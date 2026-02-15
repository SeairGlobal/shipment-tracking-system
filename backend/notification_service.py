"""
Automated Milestone Notification Service
Monitors shipments and sends automated notifications to VHC team
"""

import os
import smtplib
import schedule
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import DictCursor


class NotificationService:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'vhc_shipments'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }

        self.smtp_config = {
            'server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            'port': int(os.getenv('SMTP_PORT', '587')),
            'user': os.getenv('SMTP_USER'),
            'password': os.getenv('SMTP_PASSWORD'),
            'from_email': os.getenv('SMTP_FROM', 'notifications@seaironline.com')
        }

        # VHC notification recipients
        self.vhc_recipients = os.getenv('VHC_EMAILS', 'vhc-team@example.com').split(',')

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)

    def send_email(self, recipients, subject, html_content):
        """Send email notification"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_config['from_email']
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject

            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            with smtplib.SMTP(self.smtp_config['server'], self.smtp_config['port']) as server:
                server.starttls()
                server.login(self.smtp_config['user'], self.smtp_config['password'])
                server.send_message(msg)

            print(f"Email sent: {subject}")
            return True
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False

    def check_new_milestones(self):
        """Check for new milestones and send notifications"""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        try:
            # Get milestones from last 15 minutes that haven't been notified
            query = """
                SELECT
                    m.milestone_id, m.milestone_name, m.actual_date, m.location, m.notes,
                    s.shipment_id, s.booking_number, s.container_number, s.vessel_name
                FROM milestones m
                JOIN shipments s ON m.shipment_id = s.shipment_id
                WHERE m.notification_sent = FALSE
                  AND m.milestone_status = 'COMPLETED'
                  AND m.actual_date > NOW() - INTERVAL '15 minutes'
                ORDER BY m.actual_date DESC
            """

            cursor.execute(query)
            new_milestones = cursor.fetchall()

            for milestone in new_milestones:
                self.send_milestone_notification(milestone)

                # Mark as notified
                cursor.execute(
                    "UPDATE milestones SET notification_sent = TRUE WHERE milestone_id = %s",
                    (milestone['milestone_id'],)
                )
                conn.commit()

            print(f"Processed {len(new_milestones)} new milestones")

        except Exception as e:
            print(f"Error checking milestones: {str(e)}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    def send_milestone_notification(self, milestone):
        """Send notification for a milestone"""
        subject = f"Milestone Update: {self.format_milestone_name(milestone['milestone_name'])} - {milestone['booking_number']}"

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #1e3a8a; color: white; padding: 20px; text-align: center; }}
                .content {{ background-color: #f9fafb; padding: 20px; margin-top: 20px; border-radius: 8px; }}
                .info-row {{ margin: 10px 0; padding: 10px; background-color: white; border-left: 4px solid #1e3a8a; }}
                .label {{ font-weight: bold; color: #1e3a8a; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #6b7280; font-size: 12px; }}
                .milestone {{ background-color: #10b981; color: white; padding: 10px 20px; border-radius: 5px; display: inline-block; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Shipment Milestone Update</h1>
                </div>
                <div class="content">
                    <div class="milestone">
                        <strong>{self.format_milestone_name(milestone['milestone_name'])}</strong>
                    </div>

                    <div class="info-row">
                        <span class="label">Booking Number:</span> {milestone['booking_number']}
                    </div>
                    <div class="info-row">
                        <span class="label">Container Number:</span> {milestone['container_number'] or 'Pending'}
                    </div>
                    <div class="info-row">
                        <span class="label">Vessel:</span> {milestone['vessel_name'] or 'N/A'}
                    </div>
                    <div class="info-row">
                        <span class="label">Date/Time:</span> {milestone['actual_date'].strftime('%Y-%m-%d %H:%M UTC')}
                    </div>
                    {f'<div class="info-row"><span class="label">Location:</span> {milestone["location"]}</div>' if milestone['location'] else ''}
                    {f'<div class="info-row"><span class="label">Notes:</span> {milestone["notes"]}</div>' if milestone['notes'] else ''}

                    <p style="margin-top: 20px;">
                        Log in to the <a href="https://portal.seaironline.com">VHC Shipment Portal</a> to view full details and download documents.
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from Seair Online Shipment Management System</p>
                    <p>© {datetime.now().year} Seair Online. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        self.send_email(self.vhc_recipients, subject, html)

    def check_exceptions(self):
        """Check for new exceptions and send alerts"""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        try:
            # Get exceptions from last 15 minutes
            query = """
                SELECT
                    e.exception_id, e.exception_type, e.severity, e.title, e.description,
                    e.status, e.created_at,
                    s.booking_number, s.container_number, s.vessel_name
                FROM exceptions e
                JOIN shipments s ON e.shipment_id = s.shipment_id
                WHERE e.created_at > NOW() - INTERVAL '15 minutes'
                  AND e.status = 'OPEN'
            """

            cursor.execute(query)
            exceptions = cursor.fetchall()

            for exception in exceptions:
                self.send_exception_alert(exception)

            print(f"Processed {len(exceptions)} exceptions")

        except Exception as e:
            print(f"Error checking exceptions: {str(e)}")
        finally:
            cursor.close()
            conn.close()

    def send_exception_alert(self, exception):
        """Send alert for an exception"""
        severity_colors = {
            'LOW': '#3b82f6',
            'MEDIUM': '#f59e0b',
            'HIGH': '#ef4444',
            'CRITICAL': '#dc2626'
        }

        subject = f"🚨 Exception Alert [{exception['severity']}]: {exception['title']} - {exception['booking_number']}"

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {severity_colors.get(exception['severity'], '#ef4444')}; color: white; padding: 20px; text-align: center; }}
                .content {{ background-color: #f9fafb; padding: 20px; margin-top: 20px; border-radius: 8px; }}
                .alert {{ background-color: #fee2e2; border-left: 4px solid #dc2626; padding: 15px; margin: 15px 0; }}
                .info-row {{ margin: 10px 0; padding: 10px; background-color: white; }}
                .label {{ font-weight: bold; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚠️ Exception Alert</h1>
                    <h2>{exception['severity']} Severity</h2>
                </div>
                <div class="content">
                    <div class="alert">
                        <h3>{exception['title']}</h3>
                        <p>{exception['description'] or 'No additional details provided'}</p>
                    </div>

                    <div class="info-row">
                        <span class="label">Exception Type:</span> {exception['exception_type']}
                    </div>
                    <div class="info-row">
                        <span class="label">Booking Number:</span> {exception['booking_number']}
                    </div>
                    <div class="info-row">
                        <span class="label">Container:</span> {exception['container_number'] or 'Pending'}
                    </div>
                    <div class="info-row">
                        <span class="label">Vessel:</span> {exception['vessel_name'] or 'N/A'}
                    </div>
                    <div class="info-row">
                        <span class="label">Reported:</span> {exception['created_at'].strftime('%Y-%m-%d %H:%M UTC')}
                    </div>

                    <p style="margin-top: 20px; font-weight: bold;">
                        Immediate attention may be required. Please contact Seair operations team for updates.
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated alert from Seair Online Shipment Management System</p>
                </div>
            </div>
        </body>
        </html>
        """

        # For critical exceptions, add escalation contacts
        recipients = self.vhc_recipients.copy()
        if exception['severity'] in ['HIGH', 'CRITICAL']:
            escalation = os.getenv('ESCALATION_EMAILS', '').split(',')
            recipients.extend([e for e in escalation if e])

        self.send_email(recipients, subject, html)

    def send_daily_summary(self):
        """Send daily summary report"""
        conn = self.get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)

        try:
            # Get stats for last 24 hours
            stats = {}

            # Active shipments
            cursor.execute("SELECT COUNT(*) as count FROM shipments WHERE current_status != 'COMPLETED'")
            stats['active'] = cursor.fetchone()['count']

            # Milestones achieved today
            cursor.execute("""
                SELECT COUNT(*) as count FROM milestones
                WHERE DATE(actual_date) = CURRENT_DATE
            """)
            stats['milestones_today'] = cursor.fetchone()['count']

            # Open exceptions
            cursor.execute("SELECT COUNT(*) as count FROM exceptions WHERE status != 'RESOLVED'")
            stats['open_exceptions'] = cursor.fetchone()['count']

            # Documents uploaded today
            cursor.execute("""
                SELECT COUNT(*) as count FROM documents
                WHERE DATE(created_at) = CURRENT_DATE
            """)
            stats['docs_today'] = cursor.fetchone()['count']

            # Recent shipments
            cursor.execute("""
                SELECT booking_number, container_number, current_milestone, current_status
                FROM shipments
                WHERE current_status != 'COMPLETED'
                ORDER BY updated_at DESC
                LIMIT 10
            """)
            recent_shipments = cursor.fetchall()

            self.send_daily_summary_email(stats, recent_shipments)

        except Exception as e:
            print(f"Error generating daily summary: {str(e)}")
        finally:
            cursor.close()
            conn.close()

    def send_daily_summary_email(self, stats, shipments):
        """Send the daily summary email"""
        subject = f"Daily Shipment Summary - {datetime.now().strftime('%Y-%m-%d')}"

        shipments_html = ''.join([
            f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{s['booking_number']}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{s['container_number'] or 'Pending'}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{self.format_milestone_name(s['current_milestone'])}</td>
            </tr>
            """ for s in shipments
        ])

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #1e3a8a; color: white; padding: 20px; text-align: center; }}
                .stats {{ display: flex; justify-content: space-around; margin: 20px 0; }}
                .stat-box {{ background-color: #f3f4f6; padding: 20px; border-radius: 8px; text-align: center; flex: 1; margin: 0 10px; }}
                .stat-number {{ font-size: 36px; font-weight: bold; color: #1e3a8a; }}
                .stat-label {{ color: #6b7280; margin-top: 5px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background-color: #1e3a8a; color: white; padding: 12px; text-align: left; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Daily Shipment Summary</h1>
                    <p>{datetime.now().strftime('%B %d, %Y')}</p>
                </div>

                <div class="stats">
                    <div class="stat-box">
                        <div class="stat-number">{stats['active']}</div>
                        <div class="stat-label">Active Shipments</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{stats['milestones_today']}</div>
                        <div class="stat-label">Milestones Today</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{stats['docs_today']}</div>
                        <div class="stat-label">Docs Uploaded</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{stats['open_exceptions']}</div>
                        <div class="stat-label">Open Exceptions</div>
                    </div>
                </div>

                <h2 style="color: #1e3a8a; margin-top: 30px;">Recent Active Shipments</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Booking Number</th>
                            <th>Container</th>
                            <th>Current Milestone</th>
                        </tr>
                    </thead>
                    <tbody>
                        {shipments_html}
                    </tbody>
                </table>

                <p style="margin-top: 30px;">
                    <a href="https://portal.seaironline.com" style="background-color: #1e3a8a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        View Full Portal
                    </a>
                </p>

                <div class="footer">
                    <p>This is an automated daily summary from Seair Online</p>
                </div>
            </div>
        </body>
        </html>
        """

        self.send_email(self.vhc_recipients, subject, html)

    def format_milestone_name(self, name):
        """Format milestone name for display"""
        if not name:
            return 'N/A'
        return name.replace('_', ' ').title()

    def run(self):
        """Run the notification service"""
        print("Starting Notification Service...")
        print(f"Monitoring milestones and exceptions every 5 minutes")
        print(f"Daily summary at 08:00 UTC")

        # Schedule tasks
        schedule.every(5).minutes.do(self.check_new_milestones)
        schedule.every(5).minutes.do(self.check_exceptions)
        schedule.every().day.at("08:00").do(self.send_daily_summary)

        # Run immediately on start
        self.check_new_milestones()
        self.check_exceptions()

        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == '__main__':
    service = NotificationService()
    service.run()
