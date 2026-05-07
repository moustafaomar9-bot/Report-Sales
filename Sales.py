import streamlit as st
import pandas as pd
from fpdf import FPDF
from pathlib import Path
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import matplotlib.pyplot as plt
import os
import logging
import re
from datetime import datetime, date
import tempfile
import zipfile
from io import BytesIO

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to extract Agent Code from complex format
def extract_agent_code(code_str):
    """Extracts numeric Agent Code from strings like 'Marihan Mohamed (201120)'."""
    if isinstance(code_str, str):
        match = re.search(r'\((\d+)\)', code_str)
        return match.group(1) if match else code_str
    return str(code_str)

def get_yearly_targets(agent_code, basic_target):
    """
    Calculate targets for 2-year and 3-year cards based on BASIC TARGET (from Target file)
    Returns: (target_2years, target_3years)
    """
    # Special agent codes with fixed targets
    special_agents = {
        '201108': {'2years': 39, '3years': 13},
        '201171': {'2years': 39, '3years': 13},
        '250211': {'2years': 39, '3years': 13}
    }

    agent_code_str = str(agent_code)

    # Check if agent has special target
    if agent_code_str in special_agents:
        return special_agents[agent_code_str]['2years'], special_agents[agent_code_str]['3years']

    # Target tables based on BASIC TARGET
    targets_2years = [
        (1, 105, 8),
        (106, 125, 10),
        (126, 155, 15),
        (156, 175, 18),
        (176, 195, 20),
        (196, 220, 24),
        (221, 245, 27),
        (246, 265, 30),
        (266, 300, 36),
        (301, 320, 40)
    ]

    targets_3years = [
        (1, 105, 3),
        (106, 125, 4),
        (126, 155, 5),
        (156, 175, 6),
        (176, 195, 7),
        (196, 220, 8),
        (221, 245, 9),
        (246, 265, 10),
        (266, 300, 12),
        (301, 320, 13)
    ]

    # Find target for 2 years based on BASIC TARGET
    target_2years = 0
    for min_val, max_val, t in targets_2years:
        if min_val <= basic_target <= max_val:
            target_2years = t
            break

    # Find target for 3 years based on BASIC TARGET
    target_3years = 0
    for min_val, max_val, t in targets_3years:
        if min_val <= basic_target <= max_val:
            target_3years = t
            break

    return target_2years, target_3years

def calculate_card_status_counts(data):
    """Calculate card counts by Product Status categories without filtering for Delivery Date."""
    status_mapping = {
        'Delivered': 'Issued',
        'HC Delivery': 'Package Ready',
        'New Cards': 'Package Ready',
        'Delivery': 'Package Ready',
        'Embossed': 'Package Ready',
        'Pending Delivery': 'Package Ready',
        'Pending': 'Pending',
        'Returned': 'Pending',
        'HC Pending': 'Pending',
        'Deleted': 'Destroyed',
        'Destroyed': 'Destroyed',
        'Pending Destroyed': 'Destroyed'
    }

    data['Mapped Status'] = data['Product Status'].map(status_mapping)
    status_counts = data['Mapped Status'].value_counts().reset_index()
    status_counts.columns = ['Status', 'Count']
    total_cards = status_counts['Count'].sum()
    status_counts['Percentage'] = (status_counts['Count'] / total_cards * 100).round(2) if total_cards > 0 else 0

    return status_counts

def add_status_table_to_pdf(pdf, status_counts):
    """Add Product Status summary table to PDF."""
    logging.debug("Adding Product Status table to PDF")
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 10, "Product Status Summary", ln=True, align="C")
    pdf.ln(5)

    col_widths = [60, 30, 30]
    headers = ["Status", "Count", "Percentage (%)"]

    pdf.set_font("Arial", 'B', 5)
    pdf.set_fill_color(173, 216, 230)
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 6, header, border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Arial", '', 6)
    for _, row in status_counts.iterrows():
        if pdf.get_y() > 250:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 5)
            for i, header in enumerate(headers):
                pdf.cell(col_widths[i], 6, header, border=1, align="C", fill=True)
            pdf.ln()
            pdf.set_font("Arial", '', 6)

        pdf.cell(col_widths[0], 6, str(row['Status']), border=1, align="C")
        pdf.cell(col_widths[1], 6, str(row['Count']), border=1, align="C")
        pdf.cell(col_widths[2], 6, f"{row['Percentage']}%", border=1, align="C")
        pdf.ln()

    pdf.ln(5)
    logging.debug("Product Status table added successfully")

def add_table_header(pdf, sort_column):
    logging.debug("Adding table header")
    pdf.set_font("Arial", 'B', 5)
    headers = ["Agent", "Total", "Sec", "1Yr", "2Yr", "3Yr", "Target", "+10%", "%", "Rem"]
    header_keys = ["Agent Name", "Total Cards", "Second Cards", "1 Year Cards", "2 Years Cards", "3 Years Cards", "Basic Target", "Target +10%", "Achievement", "Remaining"]

    col_widths = [35, 12, 12, 12, 12, 12, 15, 15, 10, 12]

    for i, (header, header_key) in enumerate(zip(headers, header_keys)):
        if header_key == sort_column:
            pdf.set_fill_color(173, 216, 230)
        else:
            pdf.set_fill_color(200, 220, 255)
        pdf.cell(col_widths[i], 6, header, border=1, align="C", fill=True)
    pdf.ln()
    logging.debug("Table header added successfully")

def add_goal_status_to_pdf(pdf, two_year_cards, target_2years, three_year_cards, target_3years, total_cards, basic_target, days_worked, daily_target):
    """Add goal status section to PDF with colored progress bars"""

    pdf.set_font("Arial", 'B', 7)
    pdf.set_fill_color(240, 248, 255)
    pdf.cell(0, 6, ">>> Goal Status (Issued Card Type) <<<", ln=True, align="L", fill=True)
    pdf.ln(3)

    # 2-Year Cards Status
    pdf.set_font("Arial", 'B', 7)
    pdf.cell(60, 5, f"2-Year Cards: {two_year_cards}", ln=True)
    pdf.ln(1)

    if two_year_cards >= target_2years:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, f"Goal Met (>= {target_2years})", ln=True)
    else:
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 5, f"Goal Not Met (<{target_2years})", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # 3-Year Cards Status
    pdf.cell(60, 5, f"3-Year Cards: {three_year_cards}", ln=True)
    pdf.ln(1)

    if three_year_cards >= target_3years:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, f"Goal Met (>= {target_3years})", ln=True)
    else:
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 5, f"Goal Not Met (<{target_3years})", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Previous Balance (Daily Target Performance)
    expected_cards = daily_target * days_worked
    balance = total_cards - expected_cards

    pdf.cell(60, 5, f"Previous Balance (+/-): {int(balance)}", ln=True)
    if balance >= 0:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, f"Positive (+{int(balance)})", ln=True)
    else:
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 5, f"Negative ({int(balance)})", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Progress Toward Goals
    pdf.set_font("Arial", 'B', 7)
    pdf.set_fill_color(240, 248, 255)
    pdf.cell(0, 5, ">>> Progress Toward Goals (Issued Card Type) <<<", ln=True, align="L", fill=True)
    pdf.ln(3)

    bar_length = 50

    # 2-Year Goal Progress Bar
    pdf.set_font("Arial", 'B', 7)
    pdf.cell(0, 5, f"2-Year Goal (Min {target_2years})", ln=True)

    progress_2y = min(100, (two_year_cards / target_2years * 100)) if target_2years > 0 else 0
    filled = int(bar_length * progress_2y / 100)

    if progress_2y >= 100:
        pdf.set_fill_color(0, 150, 0)
    elif progress_2y >= 70:
        pdf.set_fill_color(255, 200, 0)
    else:
        pdf.set_fill_color(255, 100, 100)

    pdf.rect(10, pdf.get_y(), bar_length, 5, 'F')
    pdf.set_fill_color(0, 150, 0)
    pdf.rect(10, pdf.get_y(), filled, 5, 'F')
    pdf.set_y(pdf.get_y() + 5)

    pdf.set_font("Arial", '', 7)
    pdf.cell(0, 5, f"({two_year_cards}/{target_2years}) - {int(progress_2y)}%", ln=True)

    if two_year_cards >= target_2years:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, "[OK] Target Achieved!", ln=True)
    else:
        pdf.set_text_color(200, 100, 0)
        pdf.cell(0, 5, f"Need {target_2years - two_year_cards} more cards", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # 3-Year Goal Progress Bar
    pdf.set_font("Arial", 'B', 7)
    pdf.cell(0, 5, f"3-Year Goal (Min {target_3years})", ln=True)

    progress_3y = min(100, (three_year_cards / target_3years * 100)) if target_3years > 0 else 0
    filled = int(bar_length * progress_3y / 100)

    if progress_3y >= 100:
        pdf.set_fill_color(0, 150, 0)
    elif progress_3y >= 70:
        pdf.set_fill_color(255, 200, 0)
    else:
        pdf.set_fill_color(255, 100, 100)

    pdf.rect(10, pdf.get_y(), bar_length, 5, 'F')
    pdf.set_fill_color(0, 150, 0)
    pdf.rect(10, pdf.get_y(), filled, 5, 'F')
    pdf.set_y(pdf.get_y() + 5)

    pdf.set_font("Arial", '', 7)
    pdf.cell(0, 5, f"({three_year_cards}/{target_3years}) - {int(progress_3y)}%", ln=True)

    if three_year_cards >= target_3years:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, "[OK] Target Achieved!", ln=True)
    else:
        pdf.set_text_color(200, 100, 0)
        pdf.cell(0, 5, f"Need {target_3years - three_year_cards} more cards", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Daily Target Progress Bar
    pdf.set_font("Arial", 'B', 7)
    pdf.cell(0, 5, f"Daily Target Progress ({days_worked} days worked)", ln=True)

    expected_cards = daily_target * days_worked
    progress_daily = min(100, (total_cards / expected_cards * 100)) if expected_cards > 0 else 0
    filled = int(bar_length * progress_daily / 100)

    if progress_daily >= 100:
        pdf.set_fill_color(0, 150, 0)
    elif progress_daily >= 70:
        pdf.set_fill_color(255, 200, 0)
    else:
        pdf.set_fill_color(255, 100, 100)

    pdf.rect(10, pdf.get_y(), bar_length, 5, 'F')
    pdf.set_fill_color(0, 150, 0)
    pdf.rect(10, pdf.get_y(), filled, 5, 'F')
    pdf.set_y(pdf.get_y() + 5)

    pdf.set_font("Arial", '', 7)
    pdf.cell(0, 5, f"({total_cards}/{int(expected_cards)}) - {int(progress_daily)}%", ln=True)

    if progress_daily >= 100:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, f"[Excellent] You are ahead by {int(total_cards - expected_cards)} cards!", ln=True)
    elif progress_daily >= 70:
        pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 5, f"[Good] Need {int(expected_cards - total_cards)} more cards to reach target", ln=True)
    else:
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 5, f"[Warning] Need {int(expected_cards - total_cards)} more cards", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Main Target Progress Bar
    pdf.set_font("Arial", 'B', 7)
    pdf.cell(0, 5, f"Main Target ({total_cards}/{basic_target})", ln=True)

    progress_main = min(100, (total_cards / basic_target * 100)) if basic_target > 0 else 0
    filled = int(bar_length * progress_main / 100)

    if progress_main >= 100:
        pdf.set_fill_color(0, 150, 0)
    elif progress_main >= 70:
        pdf.set_fill_color(255, 200, 0)
    else:
        pdf.set_fill_color(255, 100, 100)

    pdf.rect(10, pdf.get_y(), bar_length, 5, 'F')
    pdf.set_fill_color(0, 150, 0)
    pdf.rect(10, pdf.get_y(), filled, 5, 'F')
    pdf.set_y(pdf.get_y() + 5)

    pdf.set_font("Arial", 'B', 7)
    if progress_main >= 100:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, f"[Excellent] {int(progress_main)}% - Target Met!", ln=True)
    elif progress_main >= 70:
        pdf.set_text_color(255, 140, 0)
        pdf.cell(0, 5, f"[Good] {int(progress_main)}% - Good Progress", ln=True)
    else:
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 5, f"[Warning] {int(progress_main)}% - Needs Improvement", ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

def send_email(sender_email, email_password, recipient_email, pdf_path, subject, body, attachment_name, cc_emails=None):
    try:
        logging.debug(f"Preparing to send email to {recipient_email} with attachment {attachment_name}")

        if not os.path.exists(pdf_path):
            logging.error(f"PDF file not found: {pdf_path}")
            return False

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        with open(pdf_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
            attachment.add_header('Content-Disposition', 'attachment', filename=attachment_name)
            msg.attach(attachment)

        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
            server.starttls()
            server.login(sender_email, email_password)
            server.send_message(msg)
            logging.info(f"Email sent successfully to {recipient_email}")

        return True

    except Exception as e:
        logging.error(f"Failed to send email to {recipient_email}: {str(e)}")
        return False

# Streamlit App
st.set_page_config(page_title="Sales Report Generator", page_icon="📊", layout="wide")

# Initialize session state
if 'sales_file' not in st.session_state:
    st.session_state.sales_file = None
    st.session_state.target_file = None
    st.session_state.email_file = None
    st.session_state.logo_path = None
    st.session_state.sender_email = None
    st.session_state.email_password = None
    st.session_state.email_subject = "Daily Sales Report"
    st.session_state.start_date = None
    st.session_state.end_date = None
    st.session_state.date_type = "Product Date"
    st.session_state.sort_column = "Agent Name"
    st.session_state.sort_order = "Ascending"
    st.session_state.days = 20
    st.session_state.days_worked = 20
    st.session_state.agent_df = pd.DataFrame()
    st.session_state.results_df = pd.DataFrame()

st.title("Sales Report Generator")

# Sidebar for file uploads and settings
with st.sidebar:
    st.header("File Uploads")

    sales_file = st.file_uploader("Import Sales File", type=['xlsx'])
    if sales_file is not None:
        st.session_state.sales_file = sales_file
        st.success("Sales file uploaded")

    target_file = st.file_uploader("Import Target File", type=['xlsx'])
    if target_file is not None:
        st.session_state.target_file = target_file
        st.success("Target file uploaded")

    email_file = st.file_uploader("Import Email List", type=['xlsx'])
    if email_file is not None:
        st.session_state.email_file = email_file
        st.success("Email list uploaded")

    logo_file = st.file_uploader("Choose Logo", type=['png', 'jpg', 'jpeg'])
    if logo_file is not None:
        st.session_state.logo_path = logo_file
        st.success("Logo uploaded")

    st.header("Settings")

    sender_email = st.text_input("Sender Email")
    if sender_email:
        st.session_state.sender_email = sender_email

    email_password = st.text_input("Email Password", type="password")
    if email_password:
        st.session_state.email_password = email_password

    email_subject = st.text_input("Email Subject", value=st.session_state.email_subject)
    if email_subject:
        st.session_state.email_subject = email_subject

    date_type = st.selectbox("Date Type", ["Product Date", "Delivery Date"])
    st.session_state.date_type = date_type

    start_date = st.date_input("Start Date", value=date(2026, 5, 1))
    st.session_state.start_date = start_date

    end_date = st.date_input("End Date", value=date(2026, 6, 1))
    st.session_state.end_date = end_date

    days = st.number_input("Number of Days for Daily Target", min_value=1, value=20)
    st.session_state.days = days

    st.header("Daily Target Settings")

    days_worked = st.number_input("Number of Days Worked So Far", min_value=1, max_value=30, value=st.session_state.days_worked)
    if st.button("Calculate Daily Performance", use_container_width=True):
        st.session_state.days_worked = days_worked
        st.success(f"Daily performance calculated for {days_worked} days!")

    st.header("Sort Options")

    sort_columns = ["Agent Name", "Total Cards", "Second Cards", "1 Year Cards", "2 Years Cards", "3 Years Cards", "Basic Target", "Target +10%", "Achievement", "Remaining"]
    sort_column = st.selectbox("Sort By", sort_columns, index=0)
    st.session_state.sort_column = sort_column

    sort_order = st.selectbox("Sort Order", ["Ascending", "Descending"])
    st.session_state.sort_order = sort_order

# Main content area
tab1, tab2, tab3, tab4 = st.tabs(["Results", "Generate Reports", "Send Emails", "Instructions"])

def update_results():
    if st.session_state.sales_file is None or st.session_state.target_file is None or st.session_state.email_file is None:
        return pd.DataFrame()

    try:
        sales_df = pd.read_excel(st.session_state.sales_file)
        target_df = pd.read_excel(st.session_state.target_file)
        email_df = pd.read_excel(st.session_state.email_file)

        target_df['Agent Code'] = target_df['Agent Code'].apply(extract_agent_code)

        required_columns = ['Agent Code', st.session_state.date_type, 'Price', 'Agent Name', 'Product Status']
        for col in required_columns:
            if col not in sales_df.columns:
                st.error(f"Sales file must contain '{col}' column.")
                return pd.DataFrame()

        start_date = st.session_state.start_date
        end_date = st.session_state.end_date

        sales_df[st.session_state.date_type] = pd.to_datetime(sales_df[st.session_state.date_type], format='%d/%m/%Y', errors='coerce').dt.date
        sales_df = sales_df.dropna(subset=[st.session_state.date_type])

        date_range_sales = sales_df[(sales_df[st.session_state.date_type] >= start_date) & (sales_df[st.session_state.date_type] <= end_date)]

        if date_range_sales.empty:
            st.warning(f"No sales data found between {start_date} and {end_date}")
            return pd.DataFrame()

        excluded_statuses = ['Destroyed', 'Pending', 'HC Pending', 'Returned']
        filtered_sales = date_range_sales
        if st.session_state.date_type == "Delivery Date":
            filtered_sales = date_range_sales[~date_range_sales['Product Status'].isin(excluded_statuses)]

        total_cards = filtered_sales.groupby('Agent Code').size()
        second_cards = filtered_sales[filtered_sales['Price'].isin([400, 430, 490, 520])].groupby('Agent Code').size()
        year1_cards = filtered_sales[filtered_sales['Price'].isin([550, 590, 650])].groupby('Agent Code').size()
        year2_cards = filtered_sales[filtered_sales['Price'].isin([900, 990, 1000])].groupby('Agent Code').size()
        year3_cards = filtered_sales[filtered_sales['Price'].isin([1300, 1290, 1350])].groupby('Agent Code').size()

        target_df['Agent Code'] = target_df['Agent Code'].astype(str)
        targets = target_df.set_index('Agent Code')['Target']
        target_10 = target_df.set_index('Agent Code')['Target 10%']
        sales_df['Agent Code'] = sales_df['Agent Code'].astype(str)
        agent_names = sales_df.groupby('Agent Code')['Agent Name'].first()

        agent_data = []
        for agent_code in total_cards.index:
            target = targets.get(agent_code, 0)
            if target <= 0:
                continue
            total = total_cards.get(agent_code, 0)
            second = second_cards.get(agent_code, 0)
            year1 = year1_cards.get(agent_code, 0)
            year2 = year2_cards.get(agent_code, 0)
            year3 = year3_cards.get(agent_code, 0)
            target_10_value = target_10.get(agent_code, 0)
            achievement = (total / target * 100) if target > 0 else 0
            remaining = target_10_value - total if target_10_value > 0 else 0
            agent_name = agent_names.get(agent_code, f"Agent {agent_code}")

            # Get yearly targets based on BASIC TARGET (from Target file)
            target_2years, target_3years = get_yearly_targets(agent_code, target)

            agent_data.append({
                "Agent Name": agent_name,
                "Agent Code": agent_code,
                "Total Cards": int(total),
                "Second Cards": int(second),
                "1 Year Cards": int(year1),
                "2 Years Cards": int(year2),
                "3 Years Cards": int(year3),
                "Basic Target": int(target),
                "Target +10%": int(target_10_value),
                "Achievement": int(achievement),
                "Remaining": int(remaining),
                "Target 2Y": int(target_2years),
                "Target 3Y": int(target_3years)
            })

        agent_df = pd.DataFrame(agent_data)
        if not agent_df.empty:
            ascending = st.session_state.sort_order == "Ascending"
            agent_df = agent_df.sort_values(by=st.session_state.sort_column, ascending=ascending)

        return agent_df

    except Exception as e:
        st.error(f"Failed to update results: {str(e)}")
        return pd.DataFrame()

def generate_individual_reports():
    if st.session_state.sales_file is None or st.session_state.target_file is None or st.session_state.email_file is None:
        st.error("Please upload sales, target, and email files.")
        return None

    try:
        sales_df = pd.read_excel(st.session_state.sales_file)
        target_df = pd.read_excel(st.session_state.target_file)
        email_df = pd.read_excel(st.session_state.email_file)

        target_df['Agent Code'] = target_df['Agent Code'].apply(extract_agent_code)

        start_date = st.session_state.start_date
        end_date = st.session_state.end_date

        sales_df[st.session_state.date_type] = pd.to_datetime(sales_df[st.session_state.date_type], format='%d/%m/%Y', errors='coerce').dt.date
        sales_df = sales_df.dropna(subset=[st.session_state.date_type])

        date_range_sales = sales_df[(sales_df[st.session_state.date_type] >= start_date) & (sales_df[st.session_state.date_type] <= end_date)]

        if date_range_sales.empty:
            st.warning(f"No sales data found")
            return None

        excluded_statuses = ['Destroyed', 'Pending', 'HC Pending', 'Returned']
        filtered_sales = date_range_sales
        if st.session_state.date_type == "Delivery Date":
            filtered_sales = date_range_sales[~date_range_sales['Product Status'].isin(excluded_statuses)]

        total_cards = filtered_sales.groupby('Agent Code').size()
        second_cards = filtered_sales[filtered_sales['Price'].isin([400, 430, 490, 520])].groupby('Agent Code').size()
        year1_cards = filtered_sales[filtered_sales['Price'].isin([550, 590, 650])].groupby('Agent Code').size()
        year2_cards = filtered_sales[filtered_sales['Price'].isin([900, 990, 1000])].groupby('Agent Code').size()
        year3_cards = filtered_sales[filtered_sales['Price'].isin([1300, 1290, 1350])].groupby('Agent Code').size()

        target_df['Agent Code'] = target_df['Agent Code'].astype(str)
        targets = target_df.set_index('Agent Code')['Target']
        target_10 = target_df.set_index('Agent Code')['Target 10%']
        sales_df['Agent Code'] = sales_df['Agent Code'].astype(str)
        agent_names = sales_df.groupby('Agent Code')['Agent Name'].first()

        output_dir = Path(tempfile.gettempdir()) / "PDF_Reports"
        output_dir.mkdir(exist_ok=True)

        pdf_files = []

        for agent_code in total_cards.index:
            target = targets.get(agent_code, 0)
            if target <= 0:
                continue
            total = total_cards.get(agent_code, 0)
            second = second_cards.get(agent_code, 0)
            year1 = year1_cards.get(agent_code, 0)
            year2 = year2_cards.get(agent_code, 0)
            year3 = year3_cards.get(agent_code, 0)
            target_10_value = target_10.get(agent_code, 0)
            achievement = (total / target * 100) if target > 0 else 0
            remaining = target_10_value - total if target_10_value > 0 else 0
            daily_target = target_10_value / st.session_state.days if target_10_value > 0 else 0
            agent_name = agent_names.get(agent_code, f"Agent {agent_code}")

            # Get yearly targets based on BASIC TARGET
            target_2years, target_3years = get_yearly_targets(agent_code, target)

            agent_sales = date_range_sales[date_range_sales['Agent Code'] == agent_code]
            status_counts = calculate_card_status_counts(agent_sales.copy())

            pdf = FPDF()
            pdf.add_page()

            if st.session_state.logo_path is not None:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_logo:
                    tmp_logo.write(st.session_state.logo_path.getvalue())
                    tmp_logo_path = tmp_logo.name
                pdf.image(tmp_logo_path, x=10, y=8, w=30)
                os.unlink(tmp_logo_path)

            pdf.set_font("Arial", 'B', 10)
            pdf.cell(0, 8, f"Sales Report - {start_date} to {end_date} ({st.session_state.date_type})", ln=True, align="C")
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 8, f"Agent: {agent_name} | Daily Target: {int(daily_target)}", ln=True, align="C")
            pdf.ln(5)

            add_status_table_to_pdf(pdf, status_counts)

            add_table_header(pdf, st.session_state.sort_column)

            pdf.set_font("Arial", '', 6)
            pdf.cell(35, 5, str(agent_name), border=1, align="C")
            pdf.cell(12, 5, str(int(total)), border=1, align="C")
            pdf.cell(12, 5, str(int(second)), border=1, align="C")
            pdf.cell(12, 5, str(int(year1)), border=1, align="C")
            pdf.cell(12, 5, str(int(year2)), border=1, align="C")
            pdf.cell(12, 5, str(int(year3)), border=1, align="C")
            pdf.cell(15, 5, str(int(target)), border=1, align="C")
            pdf.cell(15, 5, str(int(target_10_value)), border=1, align="C")
            pdf.cell(10, 5, f"{int(achievement)}%", border=1, align="C")
            pdf.cell(12, 5, str(int(remaining)), border=1, align="C")
            pdf.ln(3)

                        # Create smaller chart to fit on one page
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(3.2, 1.3), gridspec_kw={'width_ratios': [3, 1]})
            categories = ['Total', 'Sec', '1Yr', '2Yr', '3Yr']
            values = [total, second, year1, year2, year3]
            colors = ['#36A2EB', '#FF6384', '#4BC0C0', '#FF9F40', '#9966FF']
            bars = ax1.bar(categories, values, color=colors)
            ax1.set_ylabel("", fontsize=5)
            ax1.set_xlabel("", fontsize=5)
            ax1.tick_params(axis='both', labelsize=5)
            ax1.set_ylim(0, max(1, max(values)) * 1.05)

            for bar in bars:
                yval = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2, yval + max(1, max(values)) * 0.005, int(yval), ha='center', va='bottom', fontsize=5)

            ax2.barh(0, float(achievement) if isinstance(achievement, (int, float)) else 0, color='#4CAF50', height=0.3)
            ax2.set_xlim(0, max(100, float(achievement) * 1.1 if isinstance(achievement, (int, float)) else 100))
            ax2.set_yticks([])
            ax2.set_title("", fontsize=5)
            ax2.tick_params(axis='x', labelsize=5)
            ax2.spines['top'].set_visible(False)
            ax2.spines['right'].set_visible(False)
            ax2.spines['left'].set_visible(False)
            ax2.text(float(achievement) + 8 if isinstance(achievement, (int, float)) else 8, 0,
                     f"{int(achievement)}%",
                     ha='left', va='center', fontsize=6, color='black')

            plt.tight_layout(pad=0.1)
            chart_path = output_dir / f"temp_chart_{agent_code}.png"
            plt.savefig(chart_path, dpi=100, bbox_inches='tight')
            plt.close()

            pdf.ln(8)
            pdf.image(str(chart_path), x=10, y=None, w=70)
            os.remove(chart_path)

            # Add Goal Status Section with daily target
            pdf.ln(3)
            days_worked = st.session_state.get('days_worked', st.session_state.days)
            add_goal_status_to_pdf(pdf, year2, target_2years, year3, target_3years, total, target, days_worked, daily_target)

            pdf_path = output_dir / f"{agent_code}_report_{st.session_state.date_type.replace(' ', '_')}.pdf"
            pdf.output(pdf_path)
            pdf_files.append(pdf_path)

        return pdf_files

    except Exception as e:
        st.error(f"Failed to generate reports: {str(e)}")
        return None

def generate_summary_report():
    if st.session_state.sales_file is None or st.session_state.target_file is None or st.session_state.email_file is None:
        st.error("Please upload sales, target, and email files.")
        return None

    try:
        sales_df = pd.read_excel(st.session_state.sales_file)
        target_df = pd.read_excel(st.session_state.target_file)
        email_df = pd.read_excel(st.session_state.email_file)

        target_df['Agent Code'] = target_df['Agent Code'].apply(extract_agent_code)

        start_date = st.session_state.start_date
        end_date = st.session_state.end_date

        sales_df[st.session_state.date_type] = pd.to_datetime(sales_df[st.session_state.date_type], format='%d/%m/%Y', errors='coerce').dt.date
        sales_df = sales_df.dropna(subset=[st.session_state.date_type])

        date_range_sales = sales_df[(sales_df[st.session_state.date_type] >= start_date) & (sales_df[st.session_state.date_type] <= end_date)]

        if date_range_sales.empty:
            st.warning(f"No sales data found")
            return None

        excluded_statuses = ['Destroyed', 'Pending', 'HC Pending', 'Returned']
        filtered_sales = date_range_sales
        if st.session_state.date_type == "Delivery Date":
            filtered_sales = date_range_sales[~date_range_sales['Product Status'].isin(excluded_statuses)]

        total_cards = filtered_sales.groupby('Agent Code').size()
        second_cards = filtered_sales[filtered_sales['Price'].isin([400, 430, 490, 520])].groupby('Agent Code').size()
        year1_cards = filtered_sales[filtered_sales['Price'].isin([550, 590, 650])].groupby('Agent Code').size()
        year2_cards = filtered_sales[filtered_sales['Price'].isin([900, 990, 1000])].groupby('Agent Code').size()
        year3_cards = filtered_sales[filtered_sales['Price'].isin([1300, 1290, 1350])].groupby('Agent Code').size()

        target_df['Agent Code'] = target_df['Agent Code'].astype(str)
        targets = target_df.set_index('Agent Code')['Target']
        target_10 = target_df.set_index('Agent Code')['Target 10%']
        sales_df['Agent Code'] = sales_df['Agent Code'].astype(str)
        agent_names = sales_df.groupby('Agent Code')['Agent Name'].first()

        agent_data = []
        for agent_code in total_cards.index:
            target = targets.get(agent_code, 0)
            if target <= 0:
                continue
            total = total_cards.get(agent_code, 0)
            second = second_cards.get(agent_code, 0)
            year1 = year1_cards.get(agent_code, 0)
            year2 = year2_cards.get(agent_code, 0)
            year3 = year3_cards.get(agent_code, 0)
            target_10_value = target_10.get(agent_code, 0)
            achievement = (total / target * 100) if target > 0 else 0
            remaining = target_10_value - total if target_10_value > 0 else 0
            agent_name = agent_names.get(agent_code, f"Agent {agent_code}")

            # Get yearly targets based on BASIC TARGET
            target_2years, target_3years = get_yearly_targets(agent_code, target)

            agent_data.append({
                "Agent Name": agent_name,
                "Agent Code": agent_code,
                "Total Cards": int(total),
                "Second Cards": int(second),
                "1 Year Cards": int(year1),
                "2 Years Cards": int(year2),
                "3 Years Cards": int(year3),
                "Basic Target": int(target),
                "Target +10%": int(target_10_value),
                "Achievement": int(achievement),
                "Remaining": int(remaining),
                "Target 2Y": int(target_2years),
                "Target 3Y": int(target_3years)
            })

        agent_df = pd.DataFrame(agent_data)
        if agent_df.empty:
            st.warning("No agents with valid targets found.")
            return None

        ascending = st.session_state.sort_order == "Ascending"
        agent_df = agent_df.sort_values(by=st.session_state.sort_column, ascending=ascending)

        status_counts = calculate_card_status_counts(date_range_sales.copy())

        output_dir = Path(tempfile.gettempdir()) / "PDF_Reports"
        output_dir.mkdir(exist_ok=True)

        pdf = FPDF()
        pdf.add_page()

        if st.session_state.logo_path is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_logo:
                tmp_logo.write(st.session_state.logo_path.getvalue())
                tmp_logo_path = tmp_logo.name
            pdf.image(tmp_logo_path, x=10, y=8, w=30)
            os.unlink(tmp_logo_path)

        pdf.set_font("Arial", 'B', 12)
        title = f"Summary Sales Report - {start_date} to {end_date} ({st.session_state.date_type})"
        sort_info = f"Sorted by {st.session_state.sort_column} ({st.session_state.sort_order})"
        pdf.cell(0, 10, title, ln=True, align="C")
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, sort_info, ln=True, align="C")
        pdf.set_font("Arial", 'B', 10)
        pdf.ln(10)

        total_all_cards = agent_df['Total Cards'].sum() if not agent_df.empty else 0
        total_second_cards = agent_df['Second Cards'].sum() if not agent_df.empty else 0
        total_year1_cards = agent_df['1 Year Cards'].sum() if not agent_df.empty else 0
        total_year2_cards = agent_df['2 Years Cards'].sum() if not agent_df.empty else 0
        total_year3_cards = agent_df['3 Years Cards'].sum() if not agent_df.empty else 0
        total_target_2y = agent_df['Target 2Y'].sum() if not agent_df.empty else 0
        total_target_3y = agent_df['Target 3Y'].sum() if not agent_df.empty else 0
        avg_achievement = agent_df['Achievement'].mean() if not agent_df.empty else 0

        pdf.cell(0, 10, f"Total Cards Sold: {int(total_all_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total Second Cards: {int(total_second_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total 1-Year Cards: {int(total_year1_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total 2-Year Cards: {int(total_year2_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total 3-Year Cards: {int(total_year3_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Average Achievement: {int(avg_achievement)}%", ln=True, align="L")
        pdf.ln(10)

        add_status_table_to_pdf(pdf, status_counts)

        add_table_header(pdf, st.session_state.sort_column)

        pdf.set_font("Arial", '', 6)
        for _, row in agent_df.iterrows():
            if pdf.get_y() > 250:
                pdf.add_page()
                add_table_header(pdf, st.session_state.sort_column)

            pdf.cell(35, 6, str(row["Agent Name"]), border=1, align="C")
            pdf.cell(12, 6, str(row["Total Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["Second Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["1 Year Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["2 Years Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["3 Years Cards"]), border=1, align="C")
            pdf.cell(15, 6, str(row["Basic Target"]), border=1, align="C")
            pdf.cell(15, 6, str(row["Target +10%"]), border=1, align="C")
            pdf.cell(10, 6, f"{row['Achievement']}%", border=1, align="C")
            pdf.cell(12, 6, str(row["Remaining"]), border=1, align="C")
            pdf.ln()

        # Create summary chart
        fig, ax = plt.subplots(figsize=(6, 3))
        categories = ['Total', 'Sec', '1Yr', '2Yr', '3Yr']
        values = [total_all_cards, total_second_cards, total_year1_cards, total_year2_cards, total_year3_cards]
        colors = ['#36A2EB', '#FF6384', '#4BC0C0', '#FF9F40', '#9966FF']
        bars = ax.bar(categories, values, color=colors)
        ax.set_ylabel("Number of Cards")
        ax.set_xlabel("Card Type")
        ax.set_ylim(0, max(1, max(values)) * 1.2)

        for bar in bars:
            yval = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, yval + 0.02 * max(1, max(values)), int(yval), ha='center', va='bottom')

        plt.tight_layout()
        chart_path = output_dir / "summary_chart.png"
        plt.savefig(chart_path, dpi=100)
        plt.close()

        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.image(str(chart_path), x=10, y=None, w=120)
        os.remove(chart_path)

        # Add summary goal status with daily info
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(240, 248, 255)
        pdf.cell(0, 8, ">>> Team Summary - Goal Status <<<", ln=True, align="L", fill=True)
        pdf.ln(3)

        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 6, f"Total Team 2-Year Cards: {int(total_year2_cards)} / Target: {int(total_target_2y)}", ln=True)
        if total_year2_cards >= total_target_2y:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 5, f"[OK] Team Goal Met!", ln=True)
        else:
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 5, f"Need {int(total_target_2y - total_year2_cards)} more 2-Year Cards", ln=True)

        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 6, f"Total Team 3-Year Cards: {int(total_year3_cards)} / Target: {int(total_target_3y)}", ln=True)
        if total_year3_cards >= total_target_3y:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 5, f"[OK] Team Goal Met!", ln=True)
        else:
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 5, f"Need {int(total_target_3y - total_year3_cards)} more 3-Year Cards", ln=True)

        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

        # Add team daily performance summary
        days_worked = st.session_state.get('days_worked', st.session_state.days)
        total_daily_target = sum(agent_df['Target +10%']) / st.session_state.days if not agent_df.empty else 0
        expected_team_cards = total_daily_target * days_worked
        team_balance = total_all_cards - expected_team_cards

        pdf.cell(0, 6, f"Team Daily Performance ({days_worked} days worked):", ln=True)
        pdf.cell(0, 6, f"Expected Cards: {int(expected_team_cards)} | Actual: {int(total_all_cards)}", ln=True)
        if team_balance >= 0:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 5, f"Team is ahead by +{int(team_balance)} cards!", ln=True)
        else:
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 5, f"Team is behind by {int(team_balance)} cards", ln=True)

        pdf.set_text_color(0, 0, 0)

        pdf_path = output_dir / f"summary_report_{st.session_state.date_type.replace(' ', '_')}.pdf"
        pdf.output(pdf_path)

        return pdf_path

    except Exception as e:
        st.error(f"Failed to generate summary report: {str(e)}")
        return None

def generate_team_report(manager_email, agent_codes, sales_df, target_df, start_date, end_date):
    try:
        logging.debug(f"Generating team report for manager: {manager_email}, agents: {agent_codes}")

        if not agent_codes:
            logging.warning(f"No agents provided for manager {manager_email}")
            return None

        date_range_sales = sales_df[sales_df['Agent Code'].isin(agent_codes)]

        excluded_statuses = ['Destroyed', 'Pending', 'HC Pending', 'Returned']
        filtered_sales = date_range_sales
        if st.session_state.date_type == "Delivery Date":
            filtered_sales = date_range_sales[~date_range_sales['Product Status'].isin(excluded_statuses)]

        total_cards = filtered_sales.groupby('Agent Code').size()
        second_cards = filtered_sales[filtered_sales['Price'].isin([400, 430, 490, 520])].groupby('Agent Code').size()
        year1_cards = filtered_sales[filtered_sales['Price'].isin([550, 590, 650])].groupby('Agent Code').size()
        year2_cards = filtered_sales[filtered_sales['Price'].isin([900, 990, 1000])].groupby('Agent Code').size()
        year3_cards = filtered_sales[filtered_sales['Price'].isin([1300, 1290, 1350])].groupby('Agent Code').size()

        target_df['Agent Code'] = target_df['Agent Code'].apply(extract_agent_code)
        target_df['Agent Code'] = target_df['Agent Code'].astype(str)
        targets = target_df.set_index('Agent Code')['Target']
        target_10 = target_df.set_index('Agent Code')['Target 10%']
        sales_df['Agent Code'] = sales_df['Agent Code'].astype(str)
        agent_names = sales_df.groupby('Agent Code')['Agent Name'].first()

        valid_agents = [agent_code for agent_code in agent_codes if targets.get(agent_code, 0) > 0]
        if not valid_agents:
            logging.warning(f"No agents with targets found for manager {manager_email}")
            return None

        agent_data = []
        for agent_code in valid_agents:
            total = total_cards.get(agent_code, 0)
            second = second_cards.get(agent_code, 0)
            year1 = year1_cards.get(agent_code, 0)
            year2 = year2_cards.get(agent_code, 0)
            year3 = year3_cards.get(agent_code, 0)
            target = targets.get(agent_code, 0)
            target_10_value = target_10.get(agent_code, 0)
            achievement = (total / target * 100) if target > 0 else 0
            remaining = target_10_value - total if target_10_value > 0 else 0
            agent_name = agent_names.get(agent_code, f"Agent {agent_code}")

            # Get yearly targets based on BASIC TARGET
            target_2years, target_3years = get_yearly_targets(agent_code, target)

            agent_data.append({
                "Agent Name": agent_name,
                "Agent Code": agent_code,
                "Total Cards": int(total),
                "Second Cards": int(second),
                "1 Year Cards": int(year1),
                "2 Years Cards": int(year2),
                "3 Years Cards": int(year3),
                "Basic Target": int(target),
                "Target +10%": int(target_10_value),
                "Achievement": int(achievement),
                "Remaining": int(remaining),
                "Target 2Y": int(target_2years),
                "Target 3Y": int(target_3years)
            })

        agent_df = pd.DataFrame(agent_data)
        if agent_df.empty:
            logging.warning(f"No valid agent data for manager {manager_email}")
            return None

        ascending = st.session_state.sort_order == "Ascending"
        agent_df = agent_df.sort_values(by=st.session_state.sort_column, ascending=ascending)

        status_counts = calculate_card_status_counts(date_range_sales.copy())

        output_dir = Path(tempfile.gettempdir()) / "PDF_Reports"
        output_dir.mkdir(exist_ok=True)

        pdf = FPDF()
        pdf.add_page()

        if st.session_state.logo_path is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_logo:
                tmp_logo.write(st.session_state.logo_path.getvalue())
                tmp_logo_path = tmp_logo.name
            pdf.image(tmp_logo_path, x=10, y=8, w=30)
            os.unlink(tmp_logo_path)
            logging.debug("Logo added to PDF")

        pdf.set_font("Arial", 'B', 12)
        title = f"Team Sales Report - {start_date} to {end_date} ({st.session_state.date_type})"
        sort_info = f"Sorted by {st.session_state.sort_column} ({st.session_state.sort_order})"
        pdf.cell(0, 10, title, ln=True, align="C")
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, sort_info, ln=True, align="C")
        pdf.set_font("Arial", 'B', 10)
        pdf.ln(10)

        total_team_cards = agent_df['Total Cards'].sum() if not agent_df.empty else 0
        total_second_cards = agent_df['Second Cards'].sum() if not agent_df.empty else 0
        total_year1_cards = agent_df['1 Year Cards'].sum() if not agent_df.empty else 0
        total_year2_cards = agent_df['2 Years Cards'].sum() if not agent_df.empty else 0
        total_year3_cards = agent_df['3 Years Cards'].sum() if not agent_df.empty else 0
        total_target_2y = agent_df['Target 2Y'].sum() if not agent_df.empty else 0
        total_target_3y = agent_df['Target 3Y'].sum() if not agent_df.empty else 0

        pdf.cell(0, 10, f"Total Cards Sold by Team: {int(total_team_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total Second Cards: {int(total_second_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total 1-Year Cards: {int(total_year1_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total 2-Year Cards: {int(total_year2_cards)}", ln=True, align="L")
        pdf.cell(0, 10, f"Total 3-Year Cards: {int(total_year3_cards)}", ln=True, align="L")
        pdf.ln(10)

        add_status_table_to_pdf(pdf, status_counts)

        add_table_header(pdf, st.session_state.sort_column)

        pdf.set_font("Arial", '', 6)
        for _, row in agent_df.iterrows():
            if pdf.get_y() > 250:
                pdf.add_page()
                add_table_header(pdf, st.session_state.sort_column)
                logging.debug(f"Added new page for agent {row['Agent Code']} due to page boundary")

            pdf.cell(35, 6, str(row["Agent Name"]), border=1, align="C")
            pdf.cell(12, 6, str(row["Total Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["Second Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["1 Year Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["2 Years Cards"]), border=1, align="C")
            pdf.cell(12, 6, str(row["3 Years Cards"]), border=1, align="C")
            pdf.cell(15, 6, str(row["Basic Target"]), border=1, align="C")
            pdf.cell(15, 6, str(row["Target +10%"]), border=1, align="C")
            pdf.cell(10, 6, f"{row['Achievement']}%", border=1, align="C")
            pdf.cell(12, 6, str(row["Remaining"]), border=1, align="C")
            pdf.ln()

        # Create team chart
        fig, ax = plt.subplots(figsize=(6, 3))
        categories = ['Total', 'Sec', '1Yr', '2Yr', '3Yr']
        values = [total_team_cards, total_second_cards, total_year1_cards, total_year2_cards, total_year3_cards]
        colors = ['#36A2EB', '#FF6384', '#4BC0C0', '#FF9F40', '#9966FF']
        bars = ax.bar(categories, values, color=colors)
        ax.set_ylabel("Number of Cards")
        ax.set_xlabel("Card Type")
        ax.set_ylim(0, max(1, max(values)) * 1.2)

        for bar in bars:
            yval = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, yval + 0.02 * max(1, max(values)), int(yval), ha='center', va='bottom')

        plt.tight_layout()
        chart_path = output_dir / f"team_{manager_email.split('@')[0]}_chart.png"
        plt.savefig(chart_path, dpi=100)
        plt.close()

        if pdf.get_y() > 200:
            pdf.add_page()
        pdf.ln(2)
        pdf.image(str(chart_path), x=10, y=None, w=120)
        os.remove(chart_path)

        # Add team goal status
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(240, 248, 255)
        pdf.cell(0, 8, ">>> Team Goal Status <<<", ln=True, align="L", fill=True)
        pdf.ln(3)

        pdf.set_font("Arial", '', 9)
        pdf.cell(0, 6, f"Team 2-Year Cards: {int(total_year2_cards)} / Target: {int(total_target_2y)}", ln=True)
        if total_year2_cards >= total_target_2y:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 5, f"[OK] Team Goal Met!", ln=True)
        else:
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 5, f"Need {int(total_target_2y - total_year2_cards)} more 2-Year Cards", ln=True)

        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 6, f"Team 3-Year Cards: {int(total_year3_cards)} / Target: {int(total_target_3y)}", ln=True)
        if total_year3_cards >= total_target_3y:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 5, f"[OK] Team Goal Met!", ln=True)
        else:
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 5, f"Need {int(total_target_3y - total_year3_cards)} more 3-Year Cards", ln=True)

        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

        # Add team daily performance
        days_worked = st.session_state.get('days_worked', st.session_state.days)
        total_daily_target_team = (agent_df['Target +10%'] / st.session_state.days).sum() if not agent_df.empty else 0
        expected_team_cards = total_daily_target_team * days_worked
        team_balance = total_team_cards - expected_team_cards

        pdf.cell(0, 6, f"Team Daily Performance ({days_worked} days worked):", ln=True)
        pdf.cell(0, 6, f"Expected Cards: {int(expected_team_cards)} | Actual: {int(total_team_cards)}", ln=True)
        if team_balance >= 0:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 5, f"Team is ahead by +{int(team_balance)} cards!", ln=True)
        else:
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 5, f"Team is behind by {int(team_balance)} cards", ln=True)

        pdf.set_text_color(0, 0, 0)

        pdf_path = output_dir / f"team_{manager_email.split('@')[0]}_report_{st.session_state.date_type.replace(' ', '_')}.pdf"
        pdf.output(pdf_path)
        logging.info(f"Team report generated successfully: {pdf_path}")

        return pdf_path

    except Exception as e:
        logging.error(f"Failed to generate team report for {manager_email}: {str(e)}")
        return None

# Tab 1: Results
with tab1:
    st.header("Sales Results")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("Refresh Results", use_container_width=True):
            st.session_state.results_df = update_results()

    with col2:
        if st.button("Export to Excel", use_container_width=True):
            if not st.session_state.results_df.empty:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    export_cols = ["Agent Name", "Total Cards", "Second Cards", "1 Year Cards", "2 Years Cards", "3 Years Cards", "Basic Target", "Target +10%", "Achievement", "Remaining"]
                    export_df = st.session_state.results_df[export_cols]
                    export_df.to_excel(writer, index=False)
                excel_data = output.getvalue()
                st.download_button(
                    label="Download Excel",
                    data=excel_data,
                    file_name=f"sales_report_{st.session_state.date_type.replace(' ', '_')}_{st.session_state.start_date}_to_{st.session_state.end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.warning("No data to export. Please refresh results first.")

    if st.session_state.results_df.empty:
        st.info("Click 'Refresh Results' after uploading all files to view data.")
    else:
        display_cols = ["Agent Name", "Total Cards", "Second Cards", "1 Year Cards", "2 Years Cards", "3 Years Cards", "Basic Target", "Target +10%", "Achievement", "Remaining"]
        st.dataframe(
            st.session_state.results_df[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Achievement": st.column_config.NumberColumn("Achievement (%)", format="%d%%"),
                "Total Cards": st.column_config.NumberColumn(format="%d"),
                "Second Cards": st.column_config.NumberColumn(format="%d"),
                "1 Year Cards": st.column_config.NumberColumn(format="%d"),
                "2 Years Cards": st.column_config.NumberColumn(format="%d"),
                "3 Years Cards": st.column_config.NumberColumn(format="%d"),
                "Basic Target": st.column_config.NumberColumn(format="%d"),
                "Target +10%": st.column_config.NumberColumn(format="%d"),
                "Remaining": st.column_config.NumberColumn(format="%d")
            }
        )

# Tab 2: Generate Reports
with tab2:
    st.header("Generate Reports")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Generate Individual Reports", use_container_width=True):
            with st.spinner("Generating individual reports..."):
                pdf_files = generate_individual_reports()
                if pdf_files:
                    st.success(f"Successfully generated {len(pdf_files)} individual reports!")
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                        for pdf_path in pdf_files:
                            with open(pdf_path, 'rb') as f:
                                zip_file.writestr(pdf_path.name, f.read())
                    zip_buffer.seek(0)
                    st.download_button(
                        label="Download All Reports (ZIP)",
                        data=zip_buffer,
                        file_name=f"individual_reports_{st.session_state.start_date}_to_{st.session_state.end_date}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )

    with col2:
        if st.button("Generate Summary Report", use_container_width=True):
            with st.spinner("Generating summary report..."):
                pdf_path = generate_summary_report()
                if pdf_path:
                    st.success("Summary report generated successfully!")
                    with open(pdf_path, 'rb') as f:
                        st.download_button(
                            label="Download Summary Report",
                            data=f,
                            file_name=pdf_path.name,
                            mime="application/pdf",
                            use_container_width=True
                        )

# Tab 3: Send Emails
with tab3:
    st.header("Send Emails")

    # نوع الإرسال العام
    email_type = st.radio(
        "Select Email Type",
        ["Individual Agents", "Team Leaders", "Company Manager Summary"],
        horizontal=True
    )

    col1, col2 = st.columns(2)

    with col1:
        achievement_filter = st.number_input("Minimum Achievement % (Optional)", min_value=0, max_value=100, value=0)
        additional_cc = st.text_input("Additional CC Emails (comma-separated)")

        if st.session_state.email_file is not None:
            email_df = pd.read_excel(st.session_state.email_file)
            
            # تحديد عمود الإيميل تلقائياً
            email_column = None
            for col in ['Email', 'email', 'E-mail', 'Email Address', 'EMAIL']:
                if col in email_df.columns:
                    email_column = col
                    break
            
            if email_column:
                st.success(f"✅ Found email column: '{email_column}'")
            else:
                st.error("❌ No email column found! Please add a column named 'Email'")

            if email_type == "Individual Agents":
                if not st.session_state.results_df.empty:
                    agent_names = ["All"] + sorted(st.session_state.results_df['Agent Name'].tolist())
                    selected_agent = st.selectbox("Select Agent", agent_names)
                    
                    send_to = st.radio(
                        "Send report to:",
                        ["The Agent", "Agent's Manager"],
                        horizontal=True
                    )
                else:
                    st.warning("Please refresh results first.")
                    selected_agent = "All"
                    send_to = "The Agent"

            elif email_type == "Team Leaders":
                if 'Manager Email' not in email_df.columns:
                    st.error("Email file must contain 'Manager Email' column.")
                else:
                    # استخراج الفرق المتاحة
                    if 'Team Name' in email_df.columns:
                        team_names = ["All"] + sorted(email_df['Team Name'].dropna().unique().tolist())
                        selected_team = st.selectbox("Select Team Name", team_names)
                        
                        if selected_team == "All":
                            manager_names = ["All"] + sorted(email_df['Manager Email'].dropna().unique().tolist())
                        else:
                            team_managers = email_df[email_df['Team Name'] == selected_team]['Manager Email'].dropna().unique().tolist()
                            manager_names = ["All"] + sorted(team_managers)
                        
                        selected_manager = st.selectbox("Select Team Leader", manager_names)
                    else:
                        st.info("No 'Team Name' column found. Using managers only.")
                        manager_names = ["All"] + sorted(email_df['Manager Email'].dropna().unique().tolist())
                        selected_manager = st.selectbox("Select Team Leader", manager_names)
                        selected_team = "All"

    with col2:
        if email_type == "Company Manager Summary":
            summary_recipient = st.text_input("Company Manager Email")
            if summary_recipient:
                if '@' not in summary_recipient:
                    st.error("Please enter a valid email address")
        else:
            summary_recipient = None

        if st.session_state.sender_email:
            st.info(f"📧 Sender: {st.session_state.sender_email}")
        else:
            st.warning("⚠️ Configure sender email in sidebar")

    st.divider()

    # دوال مساعدة للتحقق من الإيميل
    def is_valid_email(email):
        if not email or pd.isna(email):
            return False
        email_str = str(email).strip()
        return '@' in email_str and '.' in email_str

    # ==================== قسم التحقق من صحة الإيميلات ====================
    if st.session_state.email_file is not None and not st.session_state.results_df.empty:
        with st.expander("🔍 Check Email Configuration", expanded=False):
            st.subheader("📊 Email File Preview")
            email_df = pd.read_excel(st.session_state.email_file)
            st.dataframe(email_df.head(10))
            
            st.subheader("🔗 Agent Codes Matching")
            sales_codes = set(st.session_state.results_df['Agent Code'].astype(str))
            email_codes = set(email_df['Agent Code'].astype(str))
            
            missing_codes = sales_codes - email_codes
            if missing_codes:
                st.warning(f"⚠️ {len(missing_codes)} Agent codes not found in email file: {list(missing_codes)[:5]}")
            else:
                st.success(f"✅ All {len(sales_codes)} agent codes matched!")
            
            st.subheader("📧 Email Coverage")
            valid_emails = email_df[email_df[email_column].notna() & (email_df[email_column].str.contains('@', na=False))] if email_column else pd.DataFrame()
            st.info(f"✅ {len(valid_emails)} agents have valid emails out of {len(email_df)}")
            
            if len(valid_emails) < len(email_df):
                missing_emails = email_df[email_df[email_column].isna() | ~email_df[email_column].str.contains('@', na=False)] if email_column else pd.DataFrame()
                st.warning(f"⚠️ {len(missing_emails)} agents missing valid emails")

    # ==================== دوال المعاينة ====================
    def preview_individual_report(agent_name):
        """معاينة تقرير السيلز الفردي"""
        agent_row = st.session_state.results_df[st.session_state.results_df['Agent Name'] == agent_name]
        if agent_row.empty:
            st.error(f"Agent '{agent_name}' not found")
            return None
        
        agent_code = agent_row.iloc[0]['Agent Code']
        output_dir = Path(tempfile.gettempdir()) / "PDF_Reports"
        pdf_path = output_dir / f"{agent_code}_report_{st.session_state.date_type.replace(' ', '_')}.pdf"
        
        if pdf_path.exists():
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            return pdf_bytes
        else:
            st.error(f"PDF not found for {agent_name}. Please generate reports first.")
            return None

    def preview_team_report(manager_email, team_agents):
        """معاينة تقرير الفريق"""
        if not team_agents:
            st.error(f"No agents found for this team")
            return None
        
        sales_df = pd.read_excel(st.session_state.sales_file)
        target_df = pd.read_excel(st.session_state.target_file)
        sales_df[st.session_state.date_type] = pd.to_datetime(sales_df[st.session_state.date_type], format='%d/%m/%Y', errors='coerce').dt.date
        date_range_sales = sales_df[(sales_df[st.session_state.date_type] >= st.session_state.start_date) & 
                                    (sales_df[st.session_state.date_type] <= st.session_state.end_date)]
        
        pdf_path = generate_team_report(
            manager_email, team_agents, date_range_sales, target_df,
            st.session_state.start_date, st.session_state.end_date
        )
        
        if pdf_path and pdf_path.exists():
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            return pdf_bytes
        else:
            st.error(f"Failed to generate team report")
            return None

    def preview_summary_report():
        """معاينة التقرير المجمع"""
        pdf_path = generate_summary_report()
        if pdf_path and pdf_path.exists():
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            return pdf_bytes
        else:
            st.error("Failed to generate summary report")
            return None

    # ==================== أزرار المعاينة والإرسال ====================
    
    if email_type == "Individual Agents":
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("👁️ Preview Report", use_container_width=True):
                if selected_agent != "All":
                    pdf_bytes = preview_individual_report(selected_agent)
                    if pdf_bytes:
                        st.download_button(
                            label="📄 Download PDF Preview",
                            data=pdf_bytes,
                            file_name=f"preview_{selected_agent.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                else:
                    st.warning("Please select a specific agent to preview")
        
        with col2:
            if st.button("📧 Send Report", use_container_width=True, type="primary"):
                if not st.session_state.sender_email or not st.session_state.email_password:
                    st.error("Configure sender email and password in sidebar.")
                elif st.session_state.email_file is None:
                    st.error("Upload email list file.")
                else:
                    with st.spinner("Sending emails..."):
                        email_df = pd.read_excel(st.session_state.email_file)
                        
                        # تحديد عمود الإيميل
                        email_col = None
                        for col in ['Email', 'email', 'E-mail', 'Email Address', 'EMAIL']:
                            if col in email_df.columns:
                                email_col = col
                                break
                        
                        if not email_col:
                            st.error("No email column found in email file!")
                            st.stop()
                        
                        agent_emails = email_df.set_index('Agent Code')[email_col].to_dict()
                        
                        # خريطة المديرين
                        manager_map = {}
                        for _, row in email_df.iterrows():
                            agent_code = str(row['Agent Code'])
                            manager = row.get('Manager Email', None)
                            if pd.notna(manager) and is_valid_email(manager):
                                manager_map[agent_code] = manager
                        
                        output_dir = Path(tempfile.gettempdir()) / "PDF_Reports"
                        filtered_df = st.session_state.results_df
                        if achievement_filter > 0:
                            filtered_df = filtered_df[filtered_df['Achievement'] >= achievement_filter]
                        
                        if selected_agent == "All":
                            agents_to_send = filtered_df['Agent Name'].tolist()
                        else:
                            agents_to_send = [selected_agent]
                        
                        cc_list = [email.strip() for email in additional_cc.split(',') if is_valid_email(email.strip())] if additional_cc else []
                        
                        successful = 0
                        failed = 0
                        errors = []
                        
                        progress_bar = st.progress(0)
                        for idx, agent_name in enumerate(agents_to_send):
                            progress_bar.progress((idx + 1) / len(agents_to_send))
                            
                            agent_row = filtered_df[filtered_df['Agent Name'] == agent_name]
                            if agent_row.empty:
                                errors.append(f"Agent '{agent_name}' not found in filtered data")
                                failed += 1
                                continue
                            
                            agent_code = str(agent_row.iloc[0]['Agent Code'])
                            
                            if send_to == "The Agent":
                                recipient_email = agent_emails.get(agent_code)
                            else:
                                recipient_email = manager_map.get(agent_code)
                            
                            if not recipient_email or not is_valid_email(recipient_email):
                                errors.append(f"Invalid email for {agent_name} (Code: {agent_code})")
                                failed += 1
                                continue
                            
                            pdf_path = output_dir / f"{agent_code}_report_{st.session_state.date_type.replace(' ', '_')}.pdf"
                            if not pdf_path.exists():
                                errors.append(f"PDF not found for {agent_name}")
                                failed += 1
                                continue
                            
                            total_cards = agent_row.iloc[0]['Total Cards']
                            achievement = agent_row.iloc[0]['Achievement']
                            year2_cards = agent_row.iloc[0]['2 Years Cards']
                            year3_cards = agent_row.iloc[0]['3 Years Cards']
                            target_2y = agent_row.iloc[0].get('Target 2Y', 0)
                            target_3y = agent_row.iloc[0].get('Target 3Y', 0)
                            days_worked = st.session_state.get('days_worked', st.session_state.days)
                            daily_target = agent_row.iloc[0]['Target +10%'] / st.session_state.days if st.session_state.days > 0 else 0
                            expected_cards = daily_target * days_worked
                            balance = total_cards - expected_cards

                            body = f"""Dear {recipient_email.split('@')[0]},

Please find attached the sales report for {agent_name}.

Period: {st.session_state.start_date} to {st.session_state.end_date}
Date Type: {st.session_state.date_type}

Summary:
- Total Cards Sold: {int(total_cards)}
- Achievement: {int(achievement)}%
- 2-Year Cards: {int(year2_cards)} / Target: {int(target_2y)}
- 3-Year Cards: {int(year3_cards)} / Target: {int(target_3y)}
- Daily Performance ({days_worked} days): Expected {int(expected_cards)} cards, Actual {int(total_cards)} cards
- Balance: {int(balance)} ({'Positive' if balance >= 0 else 'Negative'})

Best regards,
Sales Team"""
                            
                            if send_email(
                                st.session_state.sender_email,
                                st.session_state.email_password,
                                recipient_email,
                                pdf_path,
                                f"Sales Report: {agent_name}",
                                body,
                                pdf_path.name,
                                cc_list
                            ):
                                successful += 1
                            else:
                                failed += 1
                                errors.append(f"Failed to send to {agent_name}")
                        
                        progress_bar.empty()
                        st.success(f"✅ Sent: {successful} | ❌ Failed: {failed}")
                        if errors:
                            with st.expander(f"Show {len(errors)} errors"):
                                for err in errors[:15]:
                                    st.write(f"- {err}")

    elif email_type == "Team Leaders":
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("👁️ Preview Report", use_container_width=True):
                if selected_manager != "All":
                    email_df = pd.read_excel(st.session_state.email_file)
                    
                    if selected_team != "All" and 'Team Name' in email_df.columns:
                        team_agents = email_df[email_df['Team Name'] == selected_team]['Agent Code'].astype(str).tolist()
                    else:
                        team_agents = email_df[email_df['Manager Email'] == selected_manager]['Agent Code'].astype(str).tolist()
                    
                    pdf_bytes = preview_team_report(selected_manager, team_agents)
                    if pdf_bytes:
                        st.download_button(
                            label="📄 Download PDF Preview",
                            data=pdf_bytes,
                            file_name=f"preview_team_{selected_manager.split('@')[0]}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                else:
                    st.warning("Please select a specific team leader or team to preview")
        
        with col2:
            if st.button("📧 Send Report", use_container_width=True, type="primary"):
                if not st.session_state.sender_email or not st.session_state.email_password:
                    st.error("Configure sender email and password in sidebar.")
                elif st.session_state.email_file is None:
                    st.error("Upload email list file.")
                else:
                    with st.spinner("Sending emails..."):
                        email_df = pd.read_excel(st.session_state.email_file)
                        sales_df = pd.read_excel(st.session_state.sales_file)
                        target_df = pd.read_excel(st.session_state.target_file)
                        
                        sales_df[st.session_state.date_type] = pd.to_datetime(sales_df[st.session_state.date_type], format='%d/%m/%Y', errors='coerce').dt.date
                        date_range_sales = sales_df[(sales_df[st.session_state.date_type] >= st.session_state.start_date) & 
                                                    (sales_df[st.session_state.date_type] <= st.session_state.end_date)]
                        
                        # بناء خرائط الفرق والمدراء
                        team_map = {}
                        manager_team_map = {}
                        
                        for _, row in email_df.iterrows():
                            manager = row['Manager Email']
                            agent_code = str(row['Agent Code'])
                            team_name = row.get('Team Name', None)
                            
                            if pd.notna(manager) and is_valid_email(manager):
                                if manager not in team_map:
                                    team_map[manager] = []
                                team_map[manager].append(agent_code)
                                
                                if pd.notna(team_name):
                                    if team_name not in manager_team_map:
                                        manager_team_map[team_name] = manager
                        
                        # تحديد المدراء المراد إرسال التقرير لهم
                        if selected_manager != "All":
                            managers_to_send = [selected_manager]
                        elif selected_team != "All" and 'Team Name' in email_df.columns:
                            manager_for_team = manager_team_map.get(selected_team)
                            managers_to_send = [manager_for_team] if manager_for_team else []
                        else:
                            managers_to_send = list(team_map.keys())
                        
                        cc_list = [email.strip() for email in additional_cc.split(',') if is_valid_email(email.strip())] if additional_cc else []
                        
                        successful = 0
                        failed = 0
                        errors = []
                        
                        for manager_email in managers_to_send:
                            if not manager_email:
                                failed += 1
                                continue
                            
                            if selected_team != "All" and 'Team Name' in email_df.columns:
                                team_agents = email_df[email_df['Team Name'] == selected_team]['Agent Code'].astype(str).tolist()
                            else:
                                team_agents = team_map.get(manager_email, [])
                            
                            if not team_agents:
                                errors.append(f"No agents found for manager: {manager_email}")
                                failed += 1
                                continue
                            
                            filtered_df = st.session_state.results_df
                            if achievement_filter > 0:
                                filtered_df = filtered_df[filtered_df['Achievement'] >= achievement_filter]
                            
                            valid_agents = [a for a in team_agents if a in filtered_df['Agent Code'].values]
                            if not valid_agents:
                                errors.append(f"No agents match achievement filter for: {manager_email}")
                                failed += 1
                                continue
                            
                            pdf_path = generate_team_report(
                                manager_email, valid_agents, date_range_sales, target_df,
                                st.session_state.start_date, st.session_state.end_date
                            )
                            
                            if not pdf_path:
                                errors.append(f"Failed to generate report for: {manager_email}")
                                failed += 1
                                continue
                            
                            team_data = filtered_df[filtered_df['Agent Code'].isin(valid_agents)]
                            total_cards = team_data['Total Cards'].sum() if not team_data.empty else 0
                            total_year2 = team_data['2 Years Cards'].sum() if not team_data.empty else 0
                            total_year3 = team_data['3 Years Cards'].sum() if not team_data.empty else 0
                            days_worked = st.session_state.get('days_worked', st.session_state.days)
                            total_daily_target = (team_data['Target +10%'] / st.session_state.days).sum() if not team_data.empty else 0
                            expected_cards = total_daily_target * days_worked
                            team_balance = total_cards - expected_cards
                            
                            team_name_display = selected_team if selected_team != 'All' else email_df[email_df['Manager Email'] == manager_email]['Team Name'].iloc[0] if 'Team Name' in email_df.columns else "Team"
                            
                            body = f"""Dear Team Leader,

Please find attached the team sales report.

Period: {st.session_state.start_date} to {st.session_state.end_date}
Date Type: {st.session_state.date_type}
Team: {team_name_display}

Team Summary:
- Total Cards Sold: {int(total_cards)}
- Total 2-Year Cards: {int(total_year2)}
- Total 3-Year Cards: {int(total_year3)}
- Daily Performance ({days_worked} days): Expected {int(expected_cards)} cards, Actual {int(total_cards)} cards
- Team Balance: {int(team_balance)} ({'Ahead' if team_balance >= 0 else 'Behind'})

Best regards,
Sales Team"""
                            
                            if send_email(
                                st.session_state.sender_email,
                                st.session_state.email_password,
                                manager_email,
                                pdf_path,
                                f"Team Report: {st.session_state.email_subject}",
                                body,
                                pdf_path.name,
                                cc_list
                            ):
                                successful += 1
                            else:
                                failed += 1
                                errors.append(f"Failed to send to: {manager_email}")
                        
                        st.success(f"✅ Sent to managers: {successful} | ❌ Failed: {failed}")
                        if errors:
                            with st.expander(f"Show {len(errors)} errors"):
                                for err in errors[:15]:
                                    st.write(f"- {err}")

    else:  # Company Manager Summary
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("👁️ Preview Report", use_container_width=True):
                pdf_bytes = preview_summary_report()
                if pdf_bytes:
                    st.download_button(
                        label="📄 Download PDF Preview",
                        data=pdf_bytes,
                        file_name="preview_summary_report.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
        
        with col2:
            if st.button("📧 Send Report", use_container_width=True, type="primary"):
                if not st.session_state.sender_email or not st.session_state.email_password:
                    st.error("Configure sender email and password in sidebar.")
                elif not summary_recipient or not is_valid_email(summary_recipient):
                    st.error("Enter valid company manager email.")
                else:
                    with st.spinner("Generating and sending summary report..."):
                        pdf_path = generate_summary_report()
                        
                        if pdf_path:
                            filtered_df = st.session_state.results_df
                            if achievement_filter > 0:
                                filtered_df = filtered_df[filtered_df['Achievement'] >= achievement_filter]
                            
                            total_cards = filtered_df['Total Cards'].sum() if not filtered_df.empty else 0
                            total_second = filtered_df['Second Cards'].sum() if not filtered_df.empty else 0
                            total_year1 = filtered_df['1 Year Cards'].sum() if not filtered_df.empty else 0
                            total_year2 = filtered_df['2 Years Cards'].sum() if not filtered_df.empty else 0
                            total_year3 = filtered_df['3 Years Cards'].sum() if not filtered_df.empty else 0
                            avg_achievement = filtered_df['Achievement'].mean() if not filtered_df.empty else 0
                            days_worked = st.session_state.get('days_worked', st.session_state.days)
                            total_daily_target = (filtered_df['Target +10%'] / st.session_state.days).sum() if not filtered_df.empty else 0
                            expected_cards = total_daily_target * days_worked
                            summary_balance = total_cards - expected_cards
                            total_agents = len(filtered_df)
                            agents_above = len(filtered_df[filtered_df['Achievement'] >= 100]) if not filtered_df.empty else 0
                            
                            body = f"""Dear Manager,

Please find attached the summary sales report.

Period: {st.session_state.start_date} to {st.session_state.end_date}
Date Type: {st.session_state.date_type}

Summary Report Statistics:
- Total Cards Sold: {int(total_cards)}
- Total Second Cards: {int(total_second)}
- Total 1-Year Cards: {int(total_year1)}
- Total 2-Year Cards: {int(total_year2)}
- Total 3-Year Cards: {int(total_year3)}
- Average Achievement: {int(avg_achievement)}%
- Total Agents: {total_agents}
- Agents Above Target (100%+): {agents_above}
- Agents Below Target: {total_agents - agents_above}
- Daily Performance ({days_worked} days): Expected {int(expected_cards)} cards, Actual {int(total_cards)} cards
- Overall Balance: {int(summary_balance)} ({'Positive' if summary_balance >= 0 else 'Negative'})

Best regards,
Sales Team"""
                            
                            cc_list = [email.strip() for email in additional_cc.split(',') if is_valid_email(email.strip())] if additional_cc else []
                            
                            if send_email(
                                st.session_state.sender_email,
                                st.session_state.email_password,
                                summary_recipient,
                                pdf_path,
                                f"Summary Report: {st.session_state.email_subject}",
                                body,
                                pdf_path.name,
                                cc_list
                            ):
                                st.success(f"✅ Summary report sent to {summary_recipient}")
                            else:
                                st.error("❌ Failed to send summary report")
                        else:
                            st.error("❌ Failed to generate summary report")

# Tab 4: Instructions
with tab4:
    st.header("Instructions")

    st.markdown("""
    ### How to Use the Sales Report Generator

    #### 1. File Requirements

    **Sales File (.xlsx) - Required Columns:**
    - `Agent Code` - Agent identifier
    - `Agent Name` - Full name of agent
    - `Product Date` or `Delivery Date` (depending on selection)
    - `Price` - Card price 
      - Second Cards: 400, 430, 490, 520
      - 1-Year Cards: 550, 590, 650
      - 2-Year Cards: 900, 990, 1000
      - 3-Year Cards: 1300, 1290, 1350
    - `Product Status` - Status of the product (Delivered, Pending, etc.)

    **Target File (.xlsx) - Required Columns:**
    - `Agent Code` - Agent identifier
    - `Target` - Basic sales target
    - `Target 10%` - Target plus 10%

    **Email List File (.xlsx) - Required Columns:**
    - `Agent Code` - Agent identifier
    - `Email` - Agent's email address
    - `Manager Email` - Manager's email address (optional)

    #### 2. Target Tables for 2-Year and 3-Year Cards

    **2-Year Cards Target (based on BASIC TARGET):**
    | Basic Target Range | Target 2Y Cards |
    |-------------------|-----------------|
    | 1 - 105 | 8 |
    | 106 - 125 | 10 |
    | 126 - 155 | 15 |
    | 156 - 175 | 18 |
    | 176 - 195 | 20 |
    | 196 - 220 | 24 |
    | 221 - 245 | 27 |
    | 246 - 265 | 30 |
    | 266 - 300 | 36 |
    | 301 - 320 | 40 |

    **3-Year Cards Target (based on BASIC TARGET):**
    | Basic Target Range | Target 3Y Cards |
    |-------------------|-----------------|
    | 1 - 105 | 3 |
    | 106 - 125 | 4 |
    | 126 - 155 | 5 |
    | 156 - 175 | 6 |
    | 176 - 195 | 7 |
    | 196 - 220 | 8 |
    | 221 - 245 | 9 |
    | 246 - 265 | 10 |
    | 266 - 300 | 12 |
    | 301 - 320 | 13 |

    **Special Agents (Fixed Targets):**
    - Agent Codes: 201108, 201171, 250211
    - 2-Year Target: 39
    - 3-Year Target: 13

    #### 3. Steps to Use

    1. **Upload Files** - Sales, Target, and Email files
    2. **Configure Settings** - Date range, email credentials
    3. **Refresh Results** - Click to load data
    4. **Generate Reports** - Create PDF reports
    5. **Send Emails** - Send reports to agents, managers, or company manager

    #### 4. Email Configuration for Gmail

    - Use App Password (recommended)
    - SMTP Server: smtp.gmail.com
    - Port: 587
    """)

    st.info("💡 Tip: Use achievement filter to send reports only to agents meeting minimum performance.")

# Initialize results on first load
if st.session_state.results_df.empty and st.session_state.sales_file is not None:
    st.session_state.results_df = update_results()
