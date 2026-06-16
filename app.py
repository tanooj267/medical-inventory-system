from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import mysql.connector
from mysql.connector import Error
import plotly.express as px
import logging
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from datetime import timedelta
import os
import pymysql
pymysql.install_as_MySQLdb()


# Debug print to confirm file execution
print("DEBUG: Running Tanooj's Full Working app.py -", datetime.now())

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'

EMAIL_ADDRESS = "tanoojvardhan267@gmail.com"
EMAIL_PASSWORD = "xfxqvfflinxhaogc"
RECEIVER_EMAIL = "cse22031@iiitkalyani.ac.in"

app.config['MYSQL_HOST'] = os.getenv("MYSQLHOST")
app.config['MYSQL_USER'] = os.getenv("MYSQLUSER")
app.config['MYSQL_PASSWORD'] = os.getenv("MYSQLPASSWORD")
app.config['MYSQL_DB'] = os.getenv("MYSQLDATABASE")
app.config['MYSQL_PORT'] = int(os.getenv("MYSQLPORT", 3306))

# MySQL configuration
db_config = {
        'host': app.config['MYSQL_HOST'],
        'user': app.config['MYSQL_USER'],
        'password': app.config['MYSQL_PASSWORD'],
        'database': app.config['MYSQL_DB'],
        'port': app.config['MYSQL_PORT']
    }

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_connection():

    """Create MySQL connection using connection pooling."""

    connection = None

    try:

        connection = mysql.connector.connect(

            pool_name="hospital_pool",

            pool_size=10,

            **db_config
        )

        logger.info(
            "Connection to MySQL DB successful"
        )

    except Error as e:

        logger.error(
            f"Database connection error: {e}"
        )

    return connection
def send_email_notification(item_name, quantity, limit):

    subject = "Medical Inventory Alert"

    body = f"""
ALERT: Medicine stock is below the limit.

Medicine: {item_name}
Current Quantity: {quantity}
Limit: {limit}

Please restock immediately.
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECEIVER_EMAIL

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, RECEIVER_EMAIL, msg.as_string())
        server.quit()

        print("Email alert sent")

    except Exception as e:
        print("Email error:", e)

def load_user_data():
    """Load user data from the users table."""
    connection = create_connection()
    if connection is None:
        logger.error("Failed to establish database connection in load_user_data")
        return []
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()
    return users



@app.route('/')
def login_page():
    """Render the login page."""
    return render_template('login.html')
@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        connection = create_connection()

        if connection is None:
            return "Database connection failed"

        cursor = connection.cursor(dictionary=True)

        try:
            # Check if user already exists
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            existing_user = cursor.fetchone()

            if existing_user:
                return render_template('signup.html', error="Username already exists")

            # Insert new user
            cursor.execute(
                "INSERT INTO users (username, password, access) VALUES (%s, %s, %s)",
                (username, password, "No")   # New users are normal users
            )

            connection.commit()

            return redirect(url_for('login_page'))

        except Exception as e:
            return f"Error: {str(e)}"

        finally:
            cursor.close()
            connection.close()

    return render_template('signup.html')


@app.route('/login', methods=['POST'])
def login():
    """Handle user login."""
    username = request.form['username']
    password = request.form['password']
    users = load_user_data()
    user = next((u for u in users if u['username'] == username and u['password'] == password), None)
    if user:
        session['username'] = username
        session['access'] = user['access']
        return redirect(url_for('index'))
    return render_template('login.html', error="Invalid username or password.")

@app.route('/index')
def index():
    """Render the main dashboard."""
    if 'username' not in session:
        return redirect(url_for('login_page'))
    if session.get('access') == "Yes":
        return render_template('index.html')
    return redirect(url_for('user_dashboard'))

@app.route('/user_dashboard')
def user_dashboard():
    """Render the user dashboard for non-admins."""
    if 'username' in session and session.get('access') == "No":
        return render_template('user_dashboard.html')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    """Handle user logout."""
    session.pop('username', None)
    session.pop('access', None)
    return redirect(url_for('login_page'))


@app.route('/add_inventory_form', methods=['GET', 'POST'])
def add_inventory_form():

    """Add new inventory items (admin only)."""

    if 'username' not in session or session.get('access') != "Yes":
        return redirect(url_for('index'))

    if request.method == 'POST':

        connection = None
        cursor = None

        try:

            # ==========================================
            # GET FORM DATA
            # ==========================================

            item_id = int(request.form['item_id'])

            item_name = request.form['item_name'].strip()

            quantity = int(request.form['quantity'])

            unit_price = float(request.form['unit_price'])

            expiry_date = (
                request.form['expiry_date']
                if request.form['expiry_date']
                else None
            )

            # ==========================================
            # VALIDATION
            # ==========================================

            if not item_name:

                return render_template(
                    'add_inventory_form.html',
                    error="Medicine name required"
                )

            if quantity <= 0:

                return render_template(
                    'add_inventory_form.html',
                    error="Quantity must be greater than zero"
                )

            if unit_price <= 0:

                return render_template(
                    'add_inventory_form.html',
                    error="Unit price must be greater than zero"
                )

            # ==========================================
            # DATABASE CONNECTION
            # ==========================================

            connection = create_connection()

            if connection is None:

                return render_template(
                    'add_inventory_form.html',
                    error="Database connection failed"
                )

            cursor = connection.cursor(dictionary=True)

            # ==========================================
            # CHECK ITEM ID CONSISTENCY
            # SAME ITEM ID SHOULD HAVE
            # SAME MEDICINE NAME
            # ==========================================

            cursor.execute(
                  """
                  SELECT medicine_name
                  FROM medicines
                  WHERE item_id=%s
                 """,
                  (item_id,)
                )

            existing_item = cursor.fetchone()

            # ==========================================
            # ITEM NAME MISMATCH
            # ==========================================

            if existing_item:

                existing_name = (
                    existing_item['medicine_name']
                    .strip()
                    .lower()
                )

                current_name = (
                    item_name
                    .strip()
                    .lower()
                )

                if existing_name != current_name:

                    return render_template(
                        'add_inventory_form.html',
                        item_name_mismatch=True,
                        error=(
                            f"Item ID {item_id} already "
                            f"belongs to "
                            f"{existing_item['medicine_name']}"
                        )
                    )

            # ==========================================
            # INSERT NEW INVENTORY ROW
            # ==========================================

            # check medicine exists
            cursor.execute(
                """
                SELECT *
                FROM medicines
                WHERE item_id=%s
                """,
                (item_id,)
            )

            medicine = cursor.fetchone()

            # insert medicine if not exists
            if not medicine:

                cursor.execute(
                    """
                    INSERT INTO medicines
                    (
                        item_id,
                        medicine_name,
                        current_stock
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        item_id,
                        item_name,
                        quantity
                    )
                )

            else:

                cursor.execute(
                    """
                    UPDATE medicines
                    SET current_stock=current_stock+%s
                    WHERE item_id=%s
                    """,
                    (
                        quantity,
                        item_id
                    )
                )

            # insert inventory batch
            cursor.execute(
                """
                INSERT INTO inventory
                (
                    item_id,
                    quantity,
                    unit_price,
                    expiry_date
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    item_id,
                    quantity,
                    unit_price,
                    expiry_date
                )
            )
            # Save changes
            connection.commit()

            # ==========================================
            # CHECK LOW STOCK
            # ==========================================

            check_medicine_stock(item_name)

            return redirect(url_for('index'))

        except ValueError:

            return render_template(
                'add_inventory_form.html',
                error="Invalid numeric input"
            )

        except Exception as e:

            return render_template(
                'add_inventory_form.html',
                error=f"Error: {str(e)}"
            )

        finally:

            if cursor:
                cursor.close()

            if connection and connection.is_connected():
                connection.close()

    return render_template(
        'add_inventory_form.html'
    )


@app.route('/check_inventory_form', methods=['GET', 'POST'])
def check_inventory_form():
    """Check inventory by item_id or item_name."""
    if 'username' not in session:
        return redirect(url_for('login_page'))
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        item_name = request.form.get('item_name')
        if item_id and item_name:
            return render_template('check_inventory_form.html', error="Provide either Item ID or Item Name, not both.")
        if not item_id and not item_name:
            return render_template('check_inventory_form.html', error="Provide either Item ID or Item Name.")
        connection = create_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            if item_id:
                cursor.execute("SELECT i.inventory_id,i.item_id,m.medicine_name,i.quantity,i.unit_price,i.expiry_date FROM inventory i JOIN medicines m ON i.item_id=m.item_id WHERE i.item_id=%s ORDER BY i.expiry_date", (int(item_id),))
            else:
                cursor.execute("SELECT i.inventory_id,i.item_id,m.medicine_name,i.quantity,i.unit_price,i.expiry_date FROM inventory i JOIN medicines m ON i.item_id=m.item_id WHERE LOWER(m.medicine_name)=LOWER(%s) ORDER BY i.expiry_date", (item_name,))

                
            items = cursor.fetchall()
            return render_template('check_inventory_result.html', items=items)
        finally:
            cursor.close()
            connection.close()
    return render_template('check_inventory_form.html')

@app.route('/items_below_limit')
def items_below_limit():

    if 'username' not in session:
        return redirect(url_for('login_page'))

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    items = []

    # get all medicine limits
    cursor.execute("SELECT m.item_id,m.medicine_name,m.current_stock,ml.quantity_limit FROM medicines m JOIN medicine_limits ml ON m.medicine_name=ml.item_name;")
    limits = cursor.fetchall()

    for medicine in limits:

        item_name = medicine['medicine_name']
        quantity_limit = medicine['quantity_limit']

        total_quantity = medicine['current_stock']

        # check if below limit
        if total_quantity < quantity_limit:

            items.append({
                "medicine_name":medicine['medicine_name'],
                "total_quantity": total_quantity,
                "quantity_limit": quantity_limit
            })

    cursor.close()
    conn.close()

    return render_template("items_below_limit.html", items=items)

@app.route('/expired_items')
def expired_items():
    """Show expired inventory items with a pie chart."""
    if 'username' not in session:
        return redirect(url_for('login_page'))
    connection = create_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT i.item_id,m.medicine_name,i.quantity,i.unit_price,i.expiry_date FROM inventory i JOIN medicines m ON i.item_id=m.item_id WHERE i.expiry_date<CURDATE();")
        expired_items = cursor.fetchall()
        expired_data = {}

        for item in expired_items:

             item_name = item['medicine_name']

             expired_data[item_name] = (
                 expired_data.get(item_name, 0)
                 + item['quantity']
                 )
        pie_chart_html = ""
        if expired_data:
            fig = px.pie(values=list(expired_data.values()), names=list(expired_data.keys()), 
                         title="Expired Items by Expiry Date")
            pie_chart_html = fig.to_html(full_html=False)
        return render_template('expired_items.html', items=expired_items, pie_chart_html=pie_chart_html)
    finally:
        cursor.close()
        connection.close()


@app.route('/update_inventory_form', methods=['GET', 'POST'])
def update_inventory_form():

    if 'username' not in session or session.get('access') != "Yes":
        return redirect(url_for('index'))

    inventory_rows = []

    if request.method == 'POST':

        connection = create_connection()

        if connection is None:

            return render_template(
                'update_inventory_form.html',
                error="Database connection failed",
                inventory_rows=[]
            )

        cursor = connection.cursor(dictionary=True)

        try:

            # ============================================
            # SEARCH BUTTON
            # ============================================

            if 'search' in request.form:

                item_id = request.form.get('item_id')
                item_name = request.form.get('item_name')

                if item_id:

                    cursor.execute(
                        """
                        SELECT
                            i.inventory_id,
                            i.item_id,
                            m.medicine_name,
                            i.quantity,
                            i.unit_price,
                            i.expiry_date

                        FROM inventory i

                        JOIN medicines m
                        ON i.item_id=m.item_id

                        WHERE i.item_id=%s

                        ORDER BY i.expiry_date
                        """,
                        (item_id,)
                    )

                elif item_name:

                    cursor.execute(
                        """
                        SELECT
                            i.inventory_id,
                            i.item_id,
                            m.medicine_name,
                            i.quantity,
                            i.unit_price,
                            i.expiry_date

                        FROM inventory i

                        JOIN medicines m
                        ON i.item_id=m.item_id

                        WHERE LOWER(m.medicine_name)=LOWER(%s)

                        ORDER BY i.expiry_date
                        """,
                        (item_name,)
                    )

                else:

                    return render_template(
                        'update_inventory_form.html',
                        error="Enter Item ID or Item Name",
                        inventory_rows=[]
                    )

                inventory_rows = cursor.fetchall()

                return render_template(
                    'update_inventory_form.html',
                    inventory_rows=inventory_rows
                )

            # ============================================
            # UPDATE BUTTON
            # ============================================

            elif 'update' in request.form:

                inventory_ids = request.form.getlist(
                    'inventory_id'
                )

                if not inventory_ids:

                    return render_template(
                        'update_inventory_form.html',
                        error="Select at least one batch",
                        inventory_rows=[]
                    )

                # track updated medicines
                updated_medicines = set()

                for inventory_id in inventory_ids:

                    action = request.form.get(
                        f'action_{inventory_id}'
                    )

                    quantity = request.form.get(
                        f'quantity_{inventory_id}'
                    )

                    if not quantity:
                        continue

                    quantity = int(quantity)

                    if quantity <= 0:
                        continue

                    # ====================================
                    # GET INVENTORY ROW
                    # ====================================

                    cursor.execute(
                        """
                        SELECT
                            i.inventory_id,
                            i.item_id,
                            m.medicine_name,
                            i.quantity,
                            i.unit_price,
                            i.expiry_date

                        FROM inventory i

                        JOIN medicines m
                        ON i.item_id=m.item_id

                        WHERE i.inventory_id=%s
                        """,
                        (inventory_id,)
                    )

                    item = cursor.fetchone()

                    if not item:
                        continue

                    current_quantity = item['quantity']

                    updated_medicines.add(
                        item['medicine_name']
                    )

                    # ====================================
                    # REMOVE STOCK
                    # ====================================

                    if action == 'remove':

                        # insufficient stock check

                        if quantity > current_quantity:

                            # reload rows

                            cursor.execute(
                                """
                                SELECT
                                    i.inventory_id,
                                    i.item_id,
                                    m.medicine_name,
                                    i.quantity,
                                    i.unit_price,
                                    i.expiry_date

                                FROM inventory i

                                JOIN medicines m
                                ON i.item_id=m.item_id

                                WHERE i.item_id=%s

                                ORDER BY i.expiry_date
                                """,
                                (item['item_id'],)
                            )

                            inventory_rows = cursor.fetchall()

                            error_message = (
                                f"Insufficient stock for "
                                f"{item['medicine_name']} "
                                f"(Inventory ID: {inventory_id}). "
                                f"Available: {current_quantity}, "
                                f"Requested: {quantity}"
                            )

                            return render_template(
                                'update_inventory_form.html',
                                inventory_rows=inventory_rows,
                                error=error_message
                            )

                        new_quantity = (
                            current_quantity - quantity
                        )

                        # ====================================
                        # RECORD DEMAND HISTORY
                        # ====================================

                        cursor.execute(
                            """
                            INSERT INTO demand_history
                            (
                                item_id,
                                sale_date,
                                quantity_sold
                            )
                            VALUES
                            (
                                %s,
                                CURDATE(),
                                %s
                            )
                            """,
                            (
                                item['item_id'],
                                quantity
                            )
                        )

                    # ====================================
                    # ADD STOCK
                    # ====================================

                    else:

                        new_quantity = (
                            current_quantity + quantity
                        )

                    # ====================================
                    # DELETE EMPTY BATCH
                    # ====================================

                    if new_quantity == 0:

                        cursor.execute(
                            """
                            DELETE FROM inventory
                            WHERE inventory_id=%s
                            """,
                            (inventory_id,)
                        )

                    # ====================================
                    # UPDATE INVENTORY
                    # ====================================

                    else:

                        cursor.execute(
                            """
                            UPDATE inventory
                            SET quantity=%s
                            WHERE inventory_id=%s
                            """,
                            (
                                new_quantity,
                                inventory_id
                            )
                        )

                    # ====================================
                    # UPDATE CURRENT STOCK
                    # ====================================

                    if action == 'remove':

                        cursor.execute(
                            """
                            UPDATE medicines
                            SET current_stock =
                                current_stock - %s
                            WHERE item_id=%s
                            """,
                            (
                                quantity,
                                item['item_id']
                            )
                        )

                    else:

                        cursor.execute(
                            """
                            UPDATE medicines
                            SET current_stock =
                                current_stock + %s
                            WHERE item_id=%s
                            """,
                            (
                                quantity,
                                item['item_id']
                            )
                        )

                # ============================================
                # SAVE DATABASE CHANGES
                # ============================================

                connection.commit()

                # ============================================
                # CHECK STOCK ALERTS AFTER COMMIT
                # ============================================

                for medicine_name in updated_medicines:

                    check_medicine_stock(
                        medicine_name
                    )

                return redirect(
                    url_for('update_inventory_form')
                )

        except Exception as e:

            return render_template(
                'update_inventory_form.html',
                error=str(e),
                inventory_rows=[]
            )

        finally:

            cursor.close()
            connection.close()

    return render_template(
        'update_inventory_form.html',
        inventory_rows=[]
    )

def check_medicine_stock(item_name):

    conn = create_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            current_stock
        FROM medicines
        WHERE medicine_name=%s
        """,
        (item_name,)
    )

    result = cursor.fetchone()

    total_quantity = (
        result['current_stock']
        if result else 0
    )

    cursor.execute(
        """
        SELECT quantity_limit
        FROM medicine_limits
        WHERE item_name=%s
        """,
        (item_name,)
    )

    limit_data = cursor.fetchone()

    cursor.close()
    conn.close()

    if limit_data:

        quantity_limit = limit_data['quantity_limit']

        if total_quantity < quantity_limit:

            send_email_notification(
                item_name,
                total_quantity,
                quantity_limit
            )
def predict_demand_random_forest(item_id, days_to_predict=7):

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT sale_date, quantity_sold
    FROM demand_history
    WHERE item_id=%s
    ORDER BY sale_date
    """,(item_id,))

    data = cursor.fetchall()

    cursor.close()
    conn.close()

    if len(data) < 10:
        return None

    df = pd.DataFrame(data)

    df['sale_date'] = pd.to_datetime(df['sale_date'])

    df['day'] = df['sale_date'].dt.day
    df['month'] = df['sale_date'].dt.month
    df['weekday'] = df['sale_date'].dt.weekday

    X = df[['day','month','weekday']]
    y = df['quantity_sold']

    model = RandomForestRegressor(n_estimators=100)
    model.fit(X,y)

    last_date = df['sale_date'].max()

    predictions = []

    for i in range(1,days_to_predict+1):

        future_date = last_date + timedelta(days=i)

        future_features = [[
            future_date.day,
            future_date.month,
            future_date.weekday()
        ]]

        pred = model.predict(future_features)[0]

        predictions.append({
            "date": future_date.strftime('%Y-%m-%d'),
            "predicted_demand": round(pred)
        })

    return predictions
@app.route('/predict_demand', methods=['GET','POST'])
def predict_demand():

    prediction = None

    if request.method == 'POST':

        item_id = request.form['item_id']

        prediction = predict_demand_random_forest(item_id)

    return render_template(
        "predict_demand.html",
        prediction=prediction
    )
@app.route('/set_limit', methods=['GET','POST'])
def set_limit():

    if request.method == 'POST':

        item_name = request.form['item_name']
        quantity_limit = int(request.form['quantity_limit'])

        conn = create_connection()
        cursor = conn.cursor(dictionary=True)

        # insert or update limit
        cursor.execute("""
        INSERT INTO medicine_limits (item_name, quantity_limit)
        VALUES (%s,%s)
        ON DUPLICATE KEY UPDATE quantity_limit=%s
        """,(item_name,quantity_limit,quantity_limit))

        conn.commit()

        # check current total quantity
        cursor.execute(
                        """
                        SELECT current_stock
                        FROM medicines
                        WHERE medicine_name=%s
                        """,
                        (item_name,)
                    )

        result = cursor.fetchone()

        total_quantity = (
            result['current_stock']
            if result else 0
        )

        

        cursor.close()
        conn.close()

        # check if stock already below limit
        if total_quantity < quantity_limit:
            send_email_notification(
                item_name,
                total_quantity,
                quantity_limit
            )

        return "Limit saved successfully"

    return render_template("set_limit.html")

@app.route('/equipment', methods=['GET','POST'])
def manage_equipment():

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':

        equipment_name = request.form['equipment_name']
        quantity = int(request.form['quantity'])
        manufacturer = request.form['manufacturer']
        purchase_date = request.form['purchase_date']
        status = request.form['status']

        cursor.execute("""
        INSERT INTO medical_equipment 
        (equipment_name, quantity, manufacturer, purchase_date, status)
        VALUES (%s,%s,%s,%s,%s)
        """,(equipment_name,quantity,manufacturer,purchase_date,status))

        conn.commit()

    cursor.execute("SELECT * FROM medical_equipment")
    equipment = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("equipment.html", equipment=equipment)
@app.route('/equipment_issue', methods=['GET','POST'])
def equipment_issue():

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':

        equipment_name = request.form['equipment_name']
        doctor_id = request.form['doctor_id']
        equipment_needed = int(request.form['equipment_needed'])

        remaining = equipment_needed

        # get all available batches (latest first)
        cursor.execute("""
            SELECT *
            FROM medical_equipment
            WHERE equipment_name = %s
            AND status = 'Available'
            AND quantity > 0
            ORDER BY purchase_date DESC
        """, (equipment_name,))

        equipments = cursor.fetchall()

        for equipment in equipments:

            if remaining <= 0:
                break

            available_quantity = equipment['quantity']

            if available_quantity <= remaining:

                used_quantity = available_quantity
                remaining -= available_quantity
                new_quantity = 0

            else:

                used_quantity = remaining
                new_quantity = available_quantity - remaining
                remaining = 0

            # insert usage record
            if used_quantity > 0:
                cursor.execute("""
                    INSERT INTO equipment_usage
                    (equipment_name, doctor_id, equipment_needed, purchase_date)
                    VALUES (%s,%s,%s,%s)
                """,(equipment_name,doctor_id,used_quantity,equipment['purchase_date']))

            # update inventory
            cursor.execute("""
                UPDATE medical_equipment
                SET quantity = %s
                WHERE equipment_id = %s
            """,(new_quantity,equipment['equipment_id']))

        conn.commit()

        if remaining > 0:
            print("Not enough equipment available")

    cursor.close()
    conn.close()

    return render_template("equipment_issue.html")


@app.route('/equipment_status', methods=['GET','POST'])
def equipment_status():

    conn = create_connection()
    cursor = conn.cursor(dictionary=True)

    equipment_list = []
    usage_list = []
    total_available = None

    if request.method == 'POST':

        equipment_name = request.form['equipment_name']

        # total quantity
        cursor.execute(
            "SELECT SUM(quantity) AS total_quantity FROM medical_equipment WHERE equipment_name=%s",
            (equipment_name,)
        )
        total_available = cursor.fetchone()['total_quantity']

        # equipment records
        cursor.execute(
            "SELECT * FROM medical_equipment WHERE equipment_name=%s",
            (equipment_name,)
        )
        equipment_list = cursor.fetchall()

        # equipment usage with manufacture date
        cursor.execute("""
        SELECT eu.doctor_id, eu.equipment_needed, eu.purchase_date, eu.usage_date
        FROM equipment_usage eu
        WHERE eu.equipment_name=%s
        """,(equipment_name,))

        usage_list = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "equipment_status.html",
        equipment_list=equipment_list,
        usage_list=usage_list,
        total_available=total_available
    )


@app.route('/delete_inventory', methods=['GET', 'POST'])
def delete_inventory():

    """Delete a medicine and all its inventory batches."""

    # ==========================================
    # LOGIN CHECK
    # ==========================================

    if 'username' not in session:
        return redirect(url_for('login_page'))

    # ==========================================
    # ADMIN CHECK
    # ==========================================

    if session.get('access') != "Yes":
        return redirect(url_for('index'))

    # ==========================================
    # FORM SUBMISSION
    # ==========================================

    if request.method == 'POST':

        conn = None
        cursor = None

        try:

            item_id = request.form.get('item_id')

            # ======================================
            # VALIDATION
            # ======================================

            if not item_id:

                return render_template(
                    'delete_inventory.html',
                    error="Item ID is required"
                )

            try:

                item_id = int(item_id)

            except ValueError:

                return render_template(
                    'delete_inventory.html',
                    error="Item ID must be a number"
                )

            # ======================================
            # DATABASE CONNECTION
            # ======================================

            conn = create_connection()

            if not conn:

                return render_template(
                    'delete_inventory.html',
                    error="Database connection failed"
                )

            cursor = conn.cursor(dictionary=True)

            # ======================================
            # CHECK MEDICINE EXISTS
            # ======================================

            cursor.execute(
                """
                SELECT medicine_name
                FROM medicines
                WHERE item_id=%s
                """,
                (item_id,)
            )

            item = cursor.fetchone()

            if not item:

                return render_template(
                    'delete_inventory.html',
                    error=f"Item ID {item_id} not found"
                )

            # ======================================
            # DELETE INVENTORY BATCHES
            # ======================================

            cursor.execute(
                """
                DELETE FROM inventory
                WHERE item_id=%s
                """,
                (item_id,)
            )

            # ======================================
            # DELETE MEDICINE MASTER ROW
            # ======================================

            cursor.execute(
                """
                DELETE FROM medicines
                WHERE item_id=%s
                """,
                (item_id,)
            )

            # ======================================
            # SAVE CHANGES
            # ======================================

            conn.commit()

            return render_template(
                'delete_inventory.html',
                success=(
                    f"Successfully deleted "
                    f"Item ID {item_id}: "
                    f"{item['medicine_name']}"
                )
            )

        except Error as e:

            return render_template(
                'delete_inventory.html',
                error=f"Database error: {str(e)}"
            )

        except Exception as e:

            return render_template(
                'delete_inventory.html',
                error=f"Unexpected error: {str(e)}"
            )

        finally:

            if cursor:
                cursor.close()

            if conn and conn.is_connected():
                conn.close()

    # ==========================================
    # GET REQUEST
    # ==========================================

    return render_template('delete_inventory.html')


@app.route('/total_inventory_graph')
def total_inventory_graph():

    connection = create_connection()
    if connection is None:
        return "Database connection failed"

    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT m.medicine_name,i.quantity,i.expiry_date FROM inventory i JOIN medicines m ON i.item_id=m.item_id;")
    inventory = cursor.fetchall()

    cursor.close()
    connection.close()

    if not inventory:
        return render_template("total_inventory_graph.html", graph_html=None)

    df = pd.DataFrame(inventory)

    df['expiry_date'] = pd.to_datetime(df['expiry_date'], errors='coerce')

    current_date = datetime.now()

    # Total stock of each medicine
    total_stock = df.groupby('medicine_name')['quantity'].sum().reset_index()

    # Expired medicines
    expired_items = df[df['expiry_date'] < current_date]

    expired_stock = expired_items.groupby('medicine_name')['quantity'].sum().reset_index()

    # Merge both
    summary = pd.merge(total_stock, expired_stock, on='medicine_name', how='left')

    summary['quantity_y'] = summary['quantity_y'].fillna(0)

    summary.rename(columns={
        'quantity_x': 'Total Quantity',
        'quantity_y': 'Expired Quantity'
    }, inplace=True)

    # Hover information
    summary['hover_text'] = (
        "Medicine: " + summary['medicine_name'] +
        "<br>Total Stock: " + summary['Total Quantity'].astype(str) +
        "<br>Expired: " + summary['Expired Quantity'].astype(str)
    )

    # Pie chart
    fig = px.pie(
        summary,
        names='medicine_name',
        values='Total Quantity',
        title="Total Medicines Inventory"
    )

    fig.update_traces(
        hovertemplate='%{customdata}',
        customdata=summary['hover_text']
    )

    graph_html = fig.to_html(full_html=False)

    return render_template(
        "total_inventory_graph.html",
        graph_html=graph_html
    )


@app.route('/routes')
def list_routes():
    """Debug route to list all endpoints."""
    return '<br>'.join([f"{rule.endpoint}: {rule}" for rule in app.url_map.iter_rules()])



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
