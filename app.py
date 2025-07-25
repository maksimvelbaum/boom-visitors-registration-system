import flet as ft
import os
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import datetime
import qrcode
import io
import base64
import uuid
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

# --- SMTP ---
SMTP_SERVER = ""
SMTP_PORT = 587
SMTP_USER = ""
SMTP_PASSWORD = ""

# --- UTC Time Zone  ---
TIMEZONE_OFFSET_HOURS = 3  #Change if need
TARGET_TIMEZONE = datetime.timezone(datetime.timedelta(hours=TIMEZONE_OFFSET_HOURS))

# --- Database Settings ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+pg8000://postgres:postgres@localhost:5432/postgres")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase): pass

# --- If table exists  ---
class Registered(Base):
    __tablename__ = "registered"
    id = Column(Integer, primary_key=True, index=True)
    qr_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    surname = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    visitors_count = Column(Integer, nullable=False)
    host = Column(String, nullable=False)
    visit_date = Column(String, nullable=False)
    registration_time = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(TARGET_TIMEZONE))

class CheckIn(Base):
    __tablename__ = "check_in"
    id = Column(Integer, primary_key=True, index=True)
    qr_id = Column(String, index=True)
    check_in_time = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(TARGET_TIMEZONE))

class CheckOut(Base):
    __tablename__ = "check_out"
    id = Column(Integer, primary_key=True, index=True)
    qr_id = Column(String, index=True)
    check_out_time = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(TARGET_TIMEZONE))

# --- Access Cards ---
class AccessCard(Base):
    __tablename__ = "access_cards"
    id = Column(Integer, primary_key=True, index=True)
    qr_id = Column(String, index=True, nullable=False)
    phone_number = Column(String, nullable=False)
    card_number = Column(String, nullable=False)
    issue_time = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(TARGET_TIMEZONE))

# Create new tables if not exists
Base.metadata.create_all(bind=engine)

def main(page: ft.Page):
    page.title = "Visitor Registration System"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    last_registration_data = {}

    def register_user(e):
        if not all([name_field.value, surname_field.value, host_field.value, date_field.value, company_field.value, visitors_field.value]):
            show_transient_message(registration_view_controls, "Please fill all data.", ft.Colors.RED)
            return
        
        email_pdf_button.visible = False
        qr_image_control.visible = False
        email_sending_controls.visible = False

        db = SessionLocal()
        try:
            unique_qr_id = str(uuid.uuid4())
            new_user = Registered(
                qr_id=unique_qr_id, name=name_field.value, surname=surname_field.value,
                company_name=company_field.value, visitors_count=int(visitors_field.value),
                host=host_field.value, visit_date=date_field.value,
            )
            db.add(new_user)
            db.commit()

            qr_img = qrcode.make(unique_qr_id)
            buffer = io.BytesIO()
            qr_img.save(buffer, format="PNG")
            qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            qr_image_control.src_base64 = qr_base64
            qr_image_control.visible = True
            email_pdf_button.visible = True

            nonlocal last_registration_data
            last_registration_data = {
                "name": name_field.value, "surname": surname_field.value, "company": company_field.value,
                "visitors": visitors_field.value, "host": host_field.value, "date": date_field.value,
                "qr_base64": qr_base64
            }
            
            for field in [name_field, surname_field, host_field, date_field, company_field, visitors_field]: field.value = ""
            show_transient_message(registration_view_controls, "Registration success! QR-code created.", ft.Colors.GREEN)
        except ValueError:
            show_transient_message(registration_view_controls, "Error: Visitor count must be a number.", ft.Colors.RED)
        except Exception as ex:
            show_transient_message(registration_view_controls, f"Database error: {ex}", ft.Colors.RED)
        finally:
            db.close()
        page.update()

    def send_email_with_attachment(e):
        recipient_email = email_field.value
        if not recipient_email or "@" not in recipient_email:
            show_transient_message(registration_view_controls, "Please enter a valid email address.", ft.Colors.RED)
            return
        
        progress_ring.visible = True
        confirm_send_button.disabled = True
        page.update()

        try:
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer)
            c.setFont("Helvetica", 16)
            c.drawString(1*inch, 10.5*inch, "Guest pass")
            c.setFont("Helvetica", 12)
            c.drawString(1*inch, 9.5*inch, f"Name: {last_registration_data['name']} {last_registration_data['surname']}")
            c.drawString(1*inch, 9.2*inch, f"Company: {last_registration_data['company']}")
            c.drawString(1*inch, 8.9*inch, f"Host: {last_registration_data['host']}")
            c.drawString(1*inch, 8.6*inch, f"Date of visit: {last_registration_data['date']}")
            c.drawString(1*inch, 8.3*inch, f"Number of visitors: {last_registration_data['visitors']}")
            qr_bytes = base64.b64decode(last_registration_data['qr_base64'])
            qr_image = ImageReader(io.BytesIO(qr_bytes))
            c.drawImage(qr_image, 1*inch, 4*inch, width=3*inch, height=3*inch)
            c.drawString(1*inch, 2.5*inch, "Company Name")
            c.drawString(1*inch, 2.2*inch, "Company Adress")
            c.drawString(1*inch, 1.9*inch, "Company Adress2")
            c.drawString(1*inch, 1.6*inch, "Opening Hours:")
            c.showPage()
            c.save()
            pdf_buffer.seek(0)

            msg = MIMEMultipart()
            msg["From"] = SMTP_USER
            msg["To"] = recipient_email
            msg["Subject"] = f"Guest pass for {last_registration_data['name']} {last_registration_data['surname']}"
            msg.attach(MIMEText("<html><body><p>Hello,</p><p>In attachemts is your guest pass.</p><p>Company Name</p><p>Company Adress</p><p>Company Adress2</p><p>Opening Hours:</p><p>Monday–Friday, 08:00–16:00 (EET)</p><p>Best regards,<br>Visitors Registration system</p></body></html>", "html"))

            part = MIMEBase("application", "pdf")
            part.set_payload(pdf_buffer.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename=pass_{last_registration_data['surname']}.pdf")
            msg.attach(part)

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            
            show_transient_message(registration_view_controls, f"Guest pass successfully sent {recipient_email}", ft.Colors.GREEN)
            email_sending_controls.visible = False
            email_field.value = ""

        except Exception as ex:
            show_transient_message(registration_view_controls, f"Sending error: {ex}", ft.Colors.RED)
        finally:
            progress_ring.visible = False
            confirm_send_button.disabled = False
            page.update()

    def show_email_ui(e):
        email_sending_controls.visible = True
        page.update()

    def show_transient_message(view_controls_column, message, color):
        transient_msg_text = ft.Text(message, color=color, size=16, text_align=ft.TextAlign.CENTER, max_lines=5, data="transient")
        
        if len(view_controls_column.controls) > 0 and isinstance(view_controls_column.controls[0], ft.Text) and view_controls_column.controls[0].data == "transient":
            view_controls_column.controls.pop(0)

        view_controls_column.controls.insert(0, transient_msg_text)
        page.update()

    def check_in_user(e):
        qr_data = check_in_qr_field.value
        if not qr_data:
            show_transient_message(check_in_view_controls, "QR code field cannot be empty.", ft.Colors.RED)
            return

        db = SessionLocal()
        try:
            user = db.query(Registered).filter(Registered.qr_id == qr_data).first()
            if user:
                today_in_target_tz = datetime.datetime.now(TARGET_TIMEZONE).date()
                today_str = today_in_target_tz.strftime("%d.%m.%Y")
                
                if user.visit_date == today_str:
                    new_check_in = CheckIn(qr_id=qr_data)
                    db.add(new_check_in)
                    db.commit()
                    show_success_view("Check IN", "Welcome!", host=user.host, visitors=user.visitors_count, qr_id=qr_data)
                else:
                    show_transient_message(check_in_view_controls, f"Invalid visit date! Expected: {user.visit_date}.", ft.Colors.RED)
            else:
                show_transient_message(check_in_view_controls, "QR code not found in the database.", ft.Colors.RED)
        finally:
            db.close()
            check_in_qr_field.value = ""
            page.update()

    def check_out_user(e):
        qr_data = check_out_qr_field.value
        if not qr_data:
            show_transient_message(check_out_view_controls, "The QR code field cannot be empty.", ft.Colors.RED)
            return

        db = SessionLocal()
        try:
            user = db.query(Registered).filter(Registered.qr_id == qr_data).first()
            if user:
                new_check_out = CheckOut(qr_id=qr_data)
                db.add(new_check_out)
                db.commit()
                show_success_view("Check OUT", "We hope to welcome you back soon!", visitors=user.visitors_count)
            else:
                show_transient_message(check_out_view_controls, "QR code not found in the database.", ft.Colors.RED)
        finally:
            db.close()
            check_out_qr_field.value = ""
            page.update()

    def update_visitor_count(qr_id, new_count_field, text_control_to_update, success_view_column):
        new_count_str = new_count_field.value
        if not new_count_str or not new_count_str.isdigit():
            show_transient_message(success_view_column, "Error: Please enter a valid number.", ft.Colors.RED)
            return

        new_count = int(new_count_str)
        db = SessionLocal()
        try:
            user_to_update = db.query(Registered).filter(Registered.qr_id == qr_id).first()
            if user_to_update:
                user_to_update.visitors_count = new_count
                db.commit()
                text_control_to_update.value = f"Number of visitors: {new_count}"
                new_count_field.value = ""
                show_transient_message(success_view_column, "The number of visitors has been updated successfully!", ft.Colors.GREEN)
            else:
                show_transient_message(success_view_column, "Error: User not found for update.", ft.Colors.RED)
        except Exception as ex:
            show_transient_message(success_view_column, f"Database error: {ex}", ft.Colors.RED)
        finally:
            db.close()
        page.update()

    def show_success_view(action_type, message, host=None, visitors=None, qr_id=None):
        controls_list = [ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=100), ft.Text(message, size=30, weight=ft.FontWeight.BOLD), ft.Text(f"{action_type} Success", size=20)]
        if host: controls_list.append(ft.Text(f"Host: {host}", size=22, weight=ft.FontWeight.BOLD))
        visitors_text = ft.Text(f"Number of visitors: {visitors}", size=22, weight=ft.FontWeight.BOLD)
        if visitors is not None: controls_list.append(visitors_text)
        success_view_content = ft.Column(controls_list, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20, expand=True)

        if action_type == "Check IN" and qr_id:
            new_visitors_field = ft.TextField(label="New number of visitors", width=350, keyboard_type=ft.KeyboardType.NUMBER)
            update_button = ft.ElevatedButton("Update number of visitors", on_click=lambda e: update_visitor_count(qr_id, new_visitors_field, visitors_text, success_view_content), width=350, height=50)
            update_controls = ft.Column([ft.Divider(), ft.Text("Change the number of visitors:", size=18, weight=ft.FontWeight.BOLD), new_visitors_field, update_button], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            success_view_content.controls.append(update_controls)

        main_content.content = success_view_content
        page.update()

    def date_picked(e):
        date_field.value = e.control.value.strftime("%d.%m.%Y")
        date_picker.open = False
        page.update()

    def open_date_picker(e):
        date_picker.open = True
        page.update()
        
    def load_todays_cards():
        issued_cards_list.controls.clear()
        db = SessionLocal()
        try:
            now_in_target_tz = datetime.datetime.now(TARGET_TIMEZONE)
            today_start = now_in_target_tz.replace(hour=0, minute=0, second=0, microsecond=0)
            
            todays_cards = db.query(AccessCard).filter(AccessCard.issue_time >= today_start).order_by(AccessCard.issue_time.desc()).all()
            
            for card in todays_cards:
                local_time = card.issue_time.astimezone(TARGET_TIMEZONE)
                card_info = ft.Text(f"{local_time.strftime('%d.%m.%Y %H:%M:%S')} / {card.phone_number} / {card.card_number}")
                issued_cards_list.controls.append(card_info)
        finally:
            db.close()
        page.update()

    def add_access_card(e):
        if not all([access_qr_field.value, access_phone_field.value, access_card_field.value]):
            show_transient_message(access_cards_view_controls, "Please fill in all fields.", ft.Colors.RED)
            return

        db = SessionLocal()
        try:
            registered_user = db.query(Registered).filter(Registered.qr_id == access_qr_field.value).first()
            if not registered_user:
                show_transient_message(access_cards_view_controls, "Error: QR code not found in the system.", ft.Colors.RED)
                return

            new_card = AccessCard(qr_id=access_qr_field.value, phone_number=access_phone_field.value, card_number=access_card_field.value)
            db.add(new_card)
            db.commit()
            
            for field in [access_qr_field, access_phone_field, access_card_field]: field.value = ""
            show_transient_message(access_cards_view_controls, "Access card successfully issued!", ft.Colors.GREEN)
            load_todays_cards()
        except Exception as ex:
            show_transient_message(access_cards_view_controls, f"Database error: {ex}", ft.Colors.RED)
        finally:
            db.close()
        access_qr_field.focus()
        page.update()

    # --- UI ---
    name_field = ft.TextField(label="Name", width=400)
    surname_field = ft.TextField(label="Surname", width=400)
    company_field = ft.TextField(label="Company Name", width=400)
    visitors_field = ft.TextField(label="Visitors count", keyboard_type=ft.KeyboardType.NUMBER, width=400)
    host_field = ft.TextField(label="Host", width=400)
    date_field = ft.TextField(label="Visit Date", read_only=True, expand=True)
    date_button = ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, on_click=open_date_picker)
    date_row = ft.Row([date_field, date_button], width=400, alignment=ft.MainAxisAlignment.START)
    register_button = ft.ElevatedButton("Confirm", on_click=register_user, width=400, height=50)
    qr_image_control = ft.Image(visible=False, width=200, height=200)
    email_pdf_button = ft.ElevatedButton("Send a pass by mail", icon=ft.Icons.EMAIL, on_click=show_email_ui, visible=False, width=400, height=50)
    email_field = ft.TextField(label="Enter the recipient's email", width=400)
    confirm_send_button = ft.ElevatedButton("Send", icon=ft.Icons.SEND, on_click=send_email_with_attachment, width=400, height=50)
    email_sending_controls = ft.Column([email_field, confirm_send_button], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER, visible=False)
    progress_ring = ft.ProgressRing(visible=False)
    date_picker = ft.DatePicker(on_change=date_picked, first_date=datetime.datetime.now() - datetime.timedelta(days=1), help_text="Select date of visit")
    page.overlay.append(date_picker)

    check_in_qr_field = ft.TextField(label="Scan or Enter QR Code Data", width=400)
    check_in_button = ft.ElevatedButton("Check IN", on_click=check_in_user, width=400, height=50)
    check_out_qr_field = ft.TextField(label="Scan or Enter QR Code Data", width=400)
    check_out_button = ft.ElevatedButton("Check OUT", on_click=check_out_user, width=400, height=50)

    access_qr_field = ft.TextField(label="QR Code", width=400)
    access_phone_field = ft.TextField(label="Phone Number", width=400, keyboard_type=ft.KeyboardType.PHONE)
    access_card_field = ft.TextField(label="Access Card Number", width=400)
    add_card_button = ft.ElevatedButton("Issue an access card", on_click=add_access_card, width=400, height=50)
    issued_cards_list = ft.ListView(expand=True, spacing=10, padding=20)

        # --- (Views) ---
    registration_view_controls = ft.Column(
        [
            ft.Text("New visitor registration", size=24, weight=ft.FontWeight.BOLD), 
            name_field, surname_field, company_field, visitors_field, host_field, 
            date_row, 
            register_button, 
            qr_image_control, 
            email_pdf_button, 
            progress_ring, 
            email_sending_controls
        ], 
        spacing=15, 
        horizontal_alignment=ft.CrossAxisAlignment.CENTER, 
        scroll=ft.ScrollMode.ADAPTIVE
    )
    
    check_in_view_controls = ft.Column(
        [
            ft.Text("Check IN", size=24, weight=ft.FontWeight.BOLD), 
            check_in_qr_field, 
            check_in_button
        ], 
        spacing=20, 
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    check_out_view_controls = ft.Column(
        [
            ft.Text("Check OUT", size=24, weight=ft.FontWeight.BOLD), 
            check_out_qr_field, 
            check_out_button
        ], 
        spacing=20, 
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    access_cards_view_controls = ft.Column(
        [
            ft.Text("Issuance of access cards", size=24, weight=ft.FontWeight.BOLD), 
            access_qr_field, 
            access_phone_field, 
            access_card_field, 
            add_card_button, 
            ft.Divider(), 
            ft.Text("Cards issued today:", size=18, weight=ft.FontWeight.BOLD), 
            issued_cards_list
        ], 
        spacing=15, 
        horizontal_alignment=ft.CrossAxisAlignment.CENTER, 
        expand=True
    )

    views = {
        0: registration_view_controls,
        1: check_in_view_controls,
        2: check_out_view_controls,
        3: access_cards_view_controls
    }

    def switch_view(selected_index):
        main_content.content = views[selected_index]
        if selected_index != 0:
            qr_image_control.visible = False
            email_pdf_button.visible = False
            email_sending_controls.visible = False
        if selected_index == 3:
            load_todays_cards()
            access_qr_field.focus()
        page.update()

    def nav_bar_changed(e):
        page.navigation_bar.selected_index = e.control.selected_index
        switch_view(e.control.selected_index)

    page.navigation_bar = ft.NavigationBar(
        selected_index=0, on_change=nav_bar_changed,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.PERSON_ADD, label="Registration"),
            ft.NavigationBarDestination(icon=ft.Icons.LOGIN, label="Check IN"),
            ft.NavigationBarDestination(icon=ft.Icons.LOGOUT, label="Check OUT"),
            ft.NavigationBarDestination(icon=ft.Icons.CREDIT_CARD, label="Access Cards"),
        ]
    )

    main_content = ft.Container(content=views[0], expand=True, alignment=ft.alignment.center, padding=20)
    page.add(main_content)
    
    switch_view(0)
    page.update()


if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER, port=8550)

