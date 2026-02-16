"""
VHC Shipment Management System - Backend API
Flask-based REST API for managing consolidated shipments
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://localhost/vhc_shipments')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', '/tmp/vhc_uploads')

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'xlsx', 'xls', 'doc', 'docx', 'jpg', 'jpeg', 'png'}

db = SQLAlchemy(app)
jwt = JWTManager(app)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# Helper Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def role_required(allowed_roles):
    """Decorator to check user roles"""
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            current_user = get_jwt_identity()
            user_role = current_user.get('role')
            if user_role not in allowed_roles:
                return jsonify({'error': 'Unauthorized access'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def send_notification_email(recipients, subject, message):
    """Send email notifications"""
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER')
        smtp_password = os.getenv('SMTP_PASSWORD')

        if not smtp_user or not smtp_password:
            print("Email credentials not configured")
            return False

        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = ', '.join(recipients) if isinstance(recipients, list) else recipients
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'html'))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False


# ==================== AUTHENTICATION ROUTES ====================

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login endpoint"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    # Query user from database
    query = """
        SELECT user_id, email, password_hash, full_name, role, team, is_active
        FROM users WHERE email = %s
    """
    result = db.session.execute(query, (email,)).fetchone()

    if not result or not check_password_hash(result[2], password):
        return jsonify({'error': 'Invalid credentials'}), 401

    if not result[6]:  # is_active
        return jsonify({'error': 'Account is inactive'}), 403

    # Update last login
    db.session.execute(
        "UPDATE users SET last_login = %s WHERE user_id = %s",
        (datetime.utcnow(), result[0])
    )
    db.session.commit()

    # Create JWT token
    access_token = create_access_token(
        identity={
            'user_id': result[0],
            'email': result[1],
            'full_name': result[3],
            'role': result[4],
            'team': result[5]
        }
    )

    return jsonify({
        'access_token': access_token,
        'user': {
            'user_id': result[0],
            'email': result[1],
            'full_name': result[3],
            'role': result[4],
            'team': result[5]
        }
    }), 200


@app.route('/api/auth/register', methods=['POST'])
@role_required(['ADMIN'])
def register_user():
    """Register new user (Admin only)"""
    data = request.get_json()

    required_fields = ['email', 'password', 'full_name', 'role']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    # Check if user exists
    existing = db.session.execute(
        "SELECT user_id FROM users WHERE email = %s",
        (data['email'],)
    ).fetchone()

    if existing:
        return jsonify({'error': 'User already exists'}), 409

    # Hash password and insert user
    password_hash = generate_password_hash(data['password'])

    query = """
        INSERT INTO users (email, password_hash, full_name, role, team, username)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING user_id
    """
    result = db.session.execute(
        query,
        (data['email'], password_hash, data['full_name'], data['role'],
         data.get('team'), data['email'].split('@')[0])
    )
    user_id = result.fetchone()[0]
    db.session.commit()

    return jsonify({'message': 'User created successfully', 'user_id': user_id}), 201


# ==================== SHIPMENT ROUTES ====================

@app.route('/api/shipments', methods=['GET'])
@jwt_required()
def get_shipments():
    """Get all shipments with filters"""
    current_user = get_jwt_identity()

    # Build query based on filters
    filters = []
    params = []

    if request.args.get('booking_number'):
        filters.append("booking_number ILIKE %s")
        params.append(f"%{request.args.get('booking_number')}%")

    if request.args.get('status'):
        filters.append("current_status = %s")
        params.append(request.args.get('status'))

    if request.args.get('container_number'):
        filters.append("container_number ILIKE %s")
        params.append(f"%{request.args.get('container_number')}%")

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    query = f"""
        SELECT
            shipment_id, booking_number, container_number, vessel_name,
            steamship_line, rail_provider, master_bl, house_bl,
            current_status, current_milestone, origin_port, destination_port,
            booking_date, vessel_departure_date, pod_date, poe_date,
            customs_release_date, pickup_date
        FROM shipments
        {where_clause}
        ORDER BY created_at DESC
        LIMIT 100
    """

    results = db.session.execute(query, params).fetchall()

    shipments = []
    for row in results:
        shipments.append({
            'shipment_id': row[0],
            'booking_number': row[1],
            'container_number': row[2],
            'vessel_name': row[3],
            'steamship_line': row[4],
            'rail_provider': row[5],
            'master_bl': row[6],
            'house_bl': row[7],
            'current_status': row[8],
            'current_milestone': row[9],
            'origin_port': row[10],
            'destination_port': row[11],
            'booking_date': row[12].isoformat() if row[12] else None,
            'vessel_departure_date': row[13].isoformat() if row[13] else None,
            'pod_date': row[14].isoformat() if row[14] else None,
            'poe_date': row[15].isoformat() if row[15] else None,
            'customs_release_date': row[16].isoformat() if row[16] else None,
            'pickup_date': row[17].isoformat() if row[17] else None
        })

    return jsonify({'shipments': shipments}), 200


@app.route('/api/shipments/<int:shipment_id>', methods=['GET'])
@jwt_required()
def get_shipment_detail(shipment_id):
    """Get detailed shipment information"""
    query = """
        SELECT
            s.*,
            COALESCE(json_agg(DISTINCT jsonb_build_object(
                'po_id', po.po_id,
                'po_number', po.po_number,
                'vendor_reference', po.vendor_reference,
                'shipper_name', sh.shipper_name
            )) FILTER (WHERE po.po_id IS NOT NULL), '[]') as purchase_orders,
            COALESCE(json_agg(DISTINCT jsonb_build_object(
                'milestone_id', m.milestone_id,
                'milestone_name', m.milestone_name,
                'status', m.milestone_status,
                'actual_date', m.actual_date
            )) FILTER (WHERE m.milestone_id IS NOT NULL), '[]') as milestones
        FROM shipments s
        LEFT JOIN purchase_orders po ON s.shipment_id = po.shipment_id
        LEFT JOIN shippers sh ON po.shipper_id = sh.shipper_id
        LEFT JOIN milestones m ON s.shipment_id = m.shipment_id
        WHERE s.shipment_id = %s
        GROUP BY s.shipment_id
    """

    result = db.session.execute(query, (shipment_id,)).fetchone()

    if not result:
        return jsonify({'error': 'Shipment not found'}), 404

    # Convert to dict (simplified for brevity)
    shipment = {
        'shipment_id': result[0],
        'booking_number': result[1],
        'container_number': result[2],
        # ... add all other fields
        'purchase_orders': result[-2],
        'milestones': result[-1]
    }

    return jsonify(shipment), 200


@app.route('/api/shipments', methods=['POST'])
@role_required(['SEAIR_ORIGIN', 'ADMIN'])
def create_shipment():
    """Create new shipment (Seair Origin team)"""
    data = request.get_json()
    current_user = get_jwt_identity()

    required_fields = ['booking_number']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    query = """
        INSERT INTO shipments (
            booking_number, origin_port, destination_port, booking_date,
            current_status, current_milestone
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING shipment_id
    """

    result = db.session.execute(
        query,
        (data['booking_number'], data.get('origin_port'), data.get('destination_port'),
         datetime.utcnow(), 'BOOKING_CREATED', 'BOOKING_CONFIRMED')
    )
    shipment_id = result.fetchone()[0]

    # Create initial milestone
    db.session.execute(
        """INSERT INTO milestones (shipment_id, milestone_name, milestone_status, actual_date, created_by)
           VALUES (%s, %s, %s, %s, %s)""",
        (shipment_id, 'BOOKING_CONFIRMED', 'COMPLETED', datetime.utcnow(), current_user['email'])
    )

    db.session.commit()

    # Send notification
    send_notification_email(
        ['vhc-team@example.com'],
        f'New Booking Created: {data["booking_number"]}',
        f'A new shipment booking has been created with booking number {data["booking_number"]}'
    )

    return jsonify({'message': 'Shipment created', 'shipment_id': shipment_id}), 201


@app.route('/api/shipments/<int:shipment_id>/milestone', methods=['POST'])
@role_required(['SEAIR_ORIGIN', 'SEAIR_US', 'ADMIN'])
def update_milestone(shipment_id):
    """Update shipment milestone"""
    data = request.get_json()
    current_user = get_jwt_identity()

    milestone_name = data.get('milestone_name')
    if not milestone_name:
        return jsonify({'error': 'milestone_name required'}), 400

    # Insert milestone
    query = """
        INSERT INTO milestones (
            shipment_id, milestone_name, milestone_status, actual_date,
            location, notes, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING milestone_id
    """

    result = db.session.execute(
        query,
        (shipment_id, milestone_name, 'COMPLETED', datetime.utcnow(),
         data.get('location'), data.get('notes'), current_user['email'])
    )
    milestone_id = result.fetchone()[0]

    # Update shipment current milestone
    db.session.execute(
        "UPDATE shipments SET current_milestone = %s, updated_at = %s WHERE shipment_id = %s",
        (milestone_name, datetime.utcnow(), shipment_id)
    )

    db.session.commit()

    # Send notification
    shipment = db.session.execute(
        "SELECT booking_number FROM shipments WHERE shipment_id = %s",
        (shipment_id,)
    ).fetchone()

    send_notification_email(
        ['vhc-team@example.com'],
        f'Milestone Update: {milestone_name}',
        f'Shipment {shipment[0]} has reached milestone: {milestone_name}'
    )

    return jsonify({'message': 'Milestone updated', 'milestone_id': milestone_id}), 200


# ==================== DOCUMENT ROUTES ====================

@app.route('/api/shipments/<int:shipment_id>/documents', methods=['GET'])
@jwt_required()
def get_shipment_documents(shipment_id):
    """Get all documents for a shipment"""
    query = """
        SELECT
            document_id, document_type, document_name, file_size,
            uploaded_by, upload_source, created_at
        FROM documents
        WHERE shipment_id = %s
        ORDER BY created_at DESC
    """

    results = db.session.execute(query, (shipment_id,)).fetchall()

    documents = []
    for row in results:
        documents.append({
            'document_id': row[0],
            'document_type': row[1],
            'document_name': row[2],
            'file_size': row[3],
            'uploaded_by': row[4],
            'upload_source': row[5],
            'created_at': row[6].isoformat() if row[6] else None
        })

    return jsonify({'documents': documents}), 200


@app.route('/api/shipments/<int:shipment_id>/documents/upload', methods=['POST'])
@jwt_required()
def upload_document(shipment_id):
    """Upload document for shipment"""
    current_user = get_jwt_identity()

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    document_type = request.form.get('document_type')

    if not document_type:
        return jsonify({'error': 'document_type required'}), 400

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{shipment_id}_{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        file.save(file_path)

        # Save to database
        query = """
            INSERT INTO documents (
                shipment_id, document_type, document_name, file_path,
                file_size, mime_type, uploaded_by, upload_source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING document_id
        """

        result = db.session.execute(
            query,
            (shipment_id, document_type, filename, file_path,
             os.path.getsize(file_path), file.content_type,
             current_user['email'], current_user['team'])
        )
        document_id = result.fetchone()[0]
        db.session.commit()

        return jsonify({
            'message': 'Document uploaded successfully',
            'document_id': document_id
        }), 201

    return jsonify({'error': 'Invalid file type'}), 400


@app.route('/api/documents/<int:document_id>/download', methods=['GET'])
@jwt_required()
def download_document(document_id):
    """Download a document"""
    query = "SELECT file_path, document_name FROM documents WHERE document_id = %s"
    result = db.session.execute(query, (document_id,)).fetchone()

    if not result:
        return jsonify({'error': 'Document not found'}), 404

    file_path, document_name = result
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found on server'}), 404

    return send_file(file_path, as_attachment=True, download_name=document_name)


# ==================== INVOICE ROUTES ====================

@app.route('/api/shipments/<int:shipment_id>/invoices', methods=['GET'])
@jwt_required()
def get_shipment_invoices(shipment_id):
    """Get all invoices for a shipment"""
    query = """
        SELECT
            invoice_id, invoice_number, invoice_date, invoice_type,
            total_amount, currency, payment_status
        FROM invoices
        WHERE shipment_id = %s
        ORDER BY invoice_date DESC
    """

    results = db.session.execute(query, (shipment_id,)).fetchall()

    invoices = []
    for row in results:
        invoices.append({
            'invoice_id': row[0],
            'invoice_number': row[1],
            'invoice_date': row[2].isoformat() if row[2] else None,
            'invoice_type': row[3],
            'total_amount': float(row[4]) if row[4] else 0,
            'currency': row[5],
            'payment_status': row[6]
        })

    return jsonify({'invoices': invoices}), 200


@app.route('/api/invoices', methods=['POST'])
@role_required(['SEAIR_US', 'ADMIN'])
def create_invoice():
    """Create new invoice"""
    data = request.get_json()

    required_fields = ['shipment_id', 'invoice_number', 'total_amount']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    query = """
        INSERT INTO invoices (
            shipment_id, invoice_number, invoice_date, invoice_type,
            freight_charges, customs_clearance, documentation_fee,
            handling_charges, rail_charges, other_charges, total_amount, currency
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING invoice_id
    """

    result = db.session.execute(
        query,
        (data['shipment_id'], data['invoice_number'], datetime.utcnow(),
         data.get('invoice_type', 'FINAL'),
         data.get('freight_charges', 0), data.get('customs_clearance', 0),
         data.get('documentation_fee', 0), data.get('handling_charges', 0),
         data.get('rail_charges', 0), data.get('other_charges', 0),
         data['total_amount'], data.get('currency', 'USD'))
    )
    invoice_id = result.fetchone()[0]
    db.session.commit()

    return jsonify({'message': 'Invoice created', 'invoice_id': invoice_id}), 201


# ==================== DASHBOARD ROUTES ====================

@app.route('/api/dashboard/stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """Get dashboard statistics"""
    stats = {}

    # Total active shipments
    result = db.session.execute(
        "SELECT COUNT(*) FROM shipments WHERE current_status != 'COMPLETED'"
    ).fetchone()
    stats['active_shipments'] = result[0]

    # Shipments by status
    results = db.session.execute(
        "SELECT current_status, COUNT(*) FROM shipments GROUP BY current_status"
    ).fetchall()
    stats['by_status'] = {row[0]: row[1] for row in results}

    # Pending exceptions
    result = db.session.execute(
        "SELECT COUNT(*) FROM exceptions WHERE status != 'RESOLVED'"
    ).fetchone()
    stats['pending_exceptions'] = result[0]

    # Recent milestones (last 7 days)
    result = db.session.execute(
        """SELECT COUNT(*) FROM milestones
           WHERE actual_date > NOW() - INTERVAL '7 days'"""
    ).fetchone()
    stats['recent_milestones'] = result[0]

    return jsonify(stats), 200


# ==================== EXCEPTION ROUTES ====================

@app.route('/api/shipments/<int:shipment_id>/exceptions', methods=['POST'])
@role_required(['SEAIR_ORIGIN', 'SEAIR_US', 'ADMIN'])
def create_exception(shipment_id):
    """Create exception/alert for shipment"""
    data = request.get_json()
    current_user = get_jwt_identity()

    query = """
        INSERT INTO exceptions (
            shipment_id, exception_type, severity, title, description,
            reported_by, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING exception_id
    """

    result = db.session.execute(
        query,
        (shipment_id, data.get('exception_type'), data.get('severity', 'MEDIUM'),
         data['title'], data.get('description'), current_user['email'], 'OPEN')
    )
    exception_id = result.fetchone()[0]
    db.session.commit()

    # Send alert
    shipment = db.session.execute(
        "SELECT booking_number FROM shipments WHERE shipment_id = %s",
        (shipment_id,)
    ).fetchone()

    send_notification_email(
        ['vhc-team@example.com', 'seair-ops@example.com'],
        f'Exception Alert: {data["title"]}',
        f'Exception reported for shipment {shipment[0]}: {data.get("description")}'
    )

    return jsonify({'message': 'Exception created', 'exception_id': exception_id}), 201


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
