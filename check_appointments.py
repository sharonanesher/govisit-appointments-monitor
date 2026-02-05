import os
import sys
import asyncio
from playwright.async_api import async_playwright
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# קריאת הגדרות מ-environment variables
GMAIL_USER = os.getenv('GMAIL_USER')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL', GMAIL_USER)

GOVISIT_URL = "https://my.govisit.gov.il/he/app/appointment/262/412010/v2/location"
BRANCHES_TO_CHECK = ["לשכת רחובות", "לשכת ראשון לציון", "לשכת רמלה"]

def check_if_should_run():
    """בודק אם צריך להמשיך לרוץ לפי קובץ הבקרה"""
    try:
        with open('KEEP_RUNNING.txt', 'r') as f:
            content = f.read().strip().lower()
            return content == 'true'
    except:
        return True  # אם אין קובץ, ממשיכים לרוץ

async def check_appointments():
    """בודק אם יש תורים פנויים בלשכות המבוקשות"""
    
    available_branches = []
    unavailable_branches = []
    errors = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] מתחבר ל-GoVisit...")
            await page.goto(GOVISIT_URL, timeout=60000)
            await page.wait_for_load_state('networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            for branch_name in BRANCHES_TO_CHECK:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] בודק {branch_name}...")
                
                try:
                    branch_element = page.locator(f'text="{branch_name}"').first
                    
                    if await branch_element.count() > 0:
                        radio_parent = branch_element.locator('xpath=ancestor::div[contains(@role, "radio")]').first
                        is_disabled = await radio_parent.get_attribute('aria-disabled')
                        
                        if is_disabled == 'false':
                            print(f"✓ נמצאו תורים פנויים ב-{branch_name}!")
                            date_element = radio_parent.locator('text=/התור הפנוי הקרוב/')
                            if await date_element.count() > 0:
                                date_text = await date_element.inner_text()
                            else:
                                date_text = "תאריך לא זמין"
                            
                            available_branches.append({
                                'name': branch_name,
                                'date_info': date_text,
                                'status': 'available'
                            })
                        else:
                            print(f"✗ אין תורים פנויים ב-{branch_name}")
                            unavailable_branches.append({
                                'name': branch_name,
                                'status': 'unavailable'
                            })
                    else:
                        print(f"⚠ לא נמצאה לשכה בשם {branch_name}")
                        errors.append(f"לא נמצאה לשכה: {branch_name}")
                        
                except Exception as e:
                    print(f"❌ שגיאה בבדיקת {branch_name}: {str(e)}")
                    errors.append(f"שגיאה ב-{branch_name}: {str(e)}")
            
        except Exception as e:
            print(f"❌ שגיאה כללית בבדיקת התורים: {str(e)}")
            errors.append(f"שגיאה כללית: {str(e)}")
        
        finally:
            await browser.close()
    
    return {
        'available': available_branches,
        'unavailable': unavailable_branches,
        'errors': errors,
        'timestamp': datetime.now()
    }

def send_daily_report_email(results):
    """שולח דוח יומי מלא - תמיד, גם אם אין תורים"""
    
    available = results['available']
    unavailable = results['unavailable']
    errors = results['errors']
    timestamp = results['timestamp']
    
    if len(available) > 0:
        subject = f"🎉 נמצאו {len(available)} תורים פנויים במשרד הפנים!"
        emoji = "🎉"
        status_color = "#28a745"
    elif len(errors) > 0:
        subject = "⚠️ דוח יומי: בעיה בבדיקת תורים"
        emoji = "⚠️"
        status_color = "#ffc107"
    else:
        subject = "📋 דוח יומי: אין תורים פנויים כרגע"
        emoji = "📋"
        status_color = "#6c757d"
    
    body = f"""
    <html>
        <body dir="rtl" style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: {status_color}; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0;">{emoji} דוח בדיקת תורים יומי</h1>
                <p style="margin: 5px 0 0 0; font-size: 14px;">{timestamp.strftime('%d/%m/%Y בשעה %H:%M')}</p>
            </div>
            
            <div style="padding: 20px; background-color: #f8f9fa;">
    """
    
    if len(available) > 0:
        body += """
                <div style="background-color: #d4edda; border-right: 4px solid #28a745; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
                    <h2 style="color: #155724; margin-top: 0;">✅ תורים פנויים נמצאו!</h2>
                    <ul style="color: #155724;">
        """
        for branch in available:
            body += f"<li style='margin-bottom: 8px;'><strong>{branch['name']}</strong><br/>{branch['date_info']}</li>"
        body += f"""
                    </ul>
                    <a href="{GOVISIT_URL}" style="display: inline-block; background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px;">👉 לחצי כאן לקביעת תור מיידי</a>
                </div>
        """
    
    if len(unavailable) > 0:
        body += """
                <div style="background-color: #fff3cd; border-right: 4px solid #ffc107; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
                    <h2 style="color: #856404; margin-top: 0;">⏳ לשכות ללא תורים כרגע</h2>
                    <ul style="color: #856404;">
        """
        for branch in unavailable:
            body += f"<li>{branch['name']} - אין תורים פנויים, תורים נוספים יתפנו בקרוב</li>"
        body += """
                    </ul>
                </div>
        """
    
    if len(errors) > 0:
        body += """
                <div style="background-color: #f8d7da; border-right: 4px solid #dc3545; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
                    <h2 style="color: #721c24; margin-top: 0;">⚠️ שגיאות</h2>
                    <ul style="color: #721c24;">
        """
        for error in errors:
            body += f"<li>{error}</li>"
        body += """
                    </ul>
                </div>
        """
    
    body += f"""
                <div style="background-color: white; padding: 15px; border-radius: 5px; border: 1px solid #dee2e6;">
                    <h3 style="margin-top: 0;">📊 סיכום הבדיקה</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">לשכות עם תורים פנויים:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold; color: #28a745;">{len(available)}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">לשכות ללא תורים:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">{len(unavailable)}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px;">שגיאות:</td>
                            <td style="padding: 8px; font-weight: bold; color: #dc3545;">{len(errors)}</td>
                        </tr>
                    </table>
                </div>
                
                <p style="text-align: center; color: #6c757d; font-size: 12px; margin-top: 20px;">
                    הבדיקה הבאה תתבצע מחר באותה שעה<br/>
                    סקריפט אוטומטי לבדיקת תורים - GoVisit Monitor
                </p>
            </div>
        </body>
    </html>
    """
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = RECIPIENT_EMAIL
    
    msg.attach(MIMEText(body, 'html', 'utf-8'))
    
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] שולח דוח יומי במייל...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print("✓ הדוח נשלח בהצלחה במייל!")
        return True
    except Exception as e:
        print(f"❌ שגיאה בשליחת מייל: {str(e)}")
        return False

async def main():
    """הפונקציה הראשית"""
    print("=" * 50)
    print(f"בודק תורים פנויים - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 50)
    
    # בדיקה אם צריך להמשיך לרוץ
    if not check_if_should_run():
        print("⏸️ הסקריפט מושבת (KEEP_RUNNING.txt = false)")
        sys.exit(0)
    
    # בדיקת תורים
    available = await check_appointments()
    
    if available is None:
        print("❌ הבדיקה נכשלה")
        sys.exit(1)
    
    # שליחת דוח
    send_daily_report_email(available)
    
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
