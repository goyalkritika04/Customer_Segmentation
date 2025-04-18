import os
import json
import random
from datetime import datetime
from flask import Flask, render_template, request, flash, redirect, url_for, Response, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Set the backend to Agg
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import sqlite3
from sqlite3 import Error
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer as Serializer

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET_KEY', 'your_default_secret_key')

# Mail configuration
app.config['MAIL_SERVER'] = 'smtp.example.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@example.com'
app.config['MAIL_PASSWORD'] = 'your-email-password'
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@example.com'

mail = Mail(app)
ts = Serializer(app.secret_key)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"

class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['username']
        self.username = user_data['username']
        self.email = user_data['email']
        self.password_hash = user_data['password']
        self.created_at = user_data.get('created_at')
        self.last_login = user_data.get('last_login')

@login_manager.user_loader
def user_loader(username):
    users = load_users()
    user_data = users.get(username)
    if user_data:
        user_data['username'] = username  # Add username to the data
        return User(user_data)
    return None

def get_db_connection():
    """Create and return a database connection"""
    conn = None
    try:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row  # This allows accessing columns by name
        return conn
    except Error as e:
        print(f"Error connecting to database: {e}")
        raise

def init_db():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    try:
        # Create users table if not exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
        ''')
        
        # Create feedback table if not exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                feedback TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(username) REFERENCES users(username)
            )
        ''')
        
        # Create user_visualizations table if not exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_visualizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                config TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(username) REFERENCES users(username)
            )
        ''')
        
        conn.commit()
    except Error as e:
        print(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()

def load_users():
    """Load users from database"""
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return {user['username']: dict(user) for user in users}

def save_users(users):
    """Save users to database"""
    conn = get_db_connection()
    try:
        for username, user_data in users.items():
            conn.execute('''
                INSERT OR REPLACE INTO users (username, email, password, created_at, last_login)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                username,
                user_data['email'],
                user_data['password'],
                user_data.get('created_at'),
                user_data.get('last_login')
            ))
        conn.commit()
    finally:
        conn.close()

def add_user(username, email, password):
    """Add a new user to the database"""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO users (username, email, password)
            VALUES (?, ?, ?)
        ''', (username, email, generate_password_hash(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_user(username, updates):
    """Update user information in database"""
    conn = get_db_connection()
    try:
        # Build the update query dynamically based on what fields are being updated
        set_clause = ', '.join(f"{key} = ?" for key in updates.keys())
        values = list(updates.values())
        values.append(username)  # For the WHERE clause
        
        conn.execute(f'''
            UPDATE users 
            SET {set_clause}
            WHERE username = ?
        ''', values)
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating user: {e}")
        return False
    finally:
        conn.close()

def get_user_visualizations(username):
    """Get saved visualizations for a user"""
    conn = get_db_connection()
    try:
        visualizations = conn.execute('''
            SELECT id, name, config, created_at 
            FROM user_visualizations 
            WHERE username = ?
            ORDER BY created_at DESC
        ''', (username,)).fetchall()
        
        return [dict(viz) for viz in visualizations]
    except Exception as e:
        app.logger.error(f"Error getting user visualizations: {str(e)}")
        return []
    finally:
        conn.close()

def get_user_by_email(email):
    """Get user by email"""
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def get_user_by_username(username):
    """Get user data by username"""
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def check_password_strength(password):
    """Check password strength and return a score (0-4)"""
    score = 0
    if len(password) >= 8:
        score += 1
    if any(c.isupper() for c in password) and any(c.islower() for c in password):
        score += 1
    if any(c.isdigit() for c in password):
        score += 1
    if any(not c.isalnum() for c in password):
        score += 1
    return score

# Initialize the database
init_db()

# Load dataset
dataset = pd.read_csv('Dataset/train.csv')
dataset['Profession'] = dataset['Profession'].fillna('Unknown')
dataset['Gender'] = dataset['Gender'].fillna('Unknown')
if 'Spending_Score' in dataset.columns:
    dataset['Spending_Score'] = dataset['Spending_Score'].fillna('Unknown')

# Template filter for JSON serialization
@app.template_filter('tojson')
def tojson_filter(obj):
    return json.dumps(obj)

# Template filter for datetime formatting
@app.template_filter('format_datetime')
def format_datetime(value, format='medium'):
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if format == 'full':
        format="EEEE, d. MMMM y 'at' HH:mm"
    elif format == 'medium':
        format="EE dd.MM.y HH:mm"
    return value.strftime(format)

# Routes
@app.route("/")
def home_page():
    return render_template("home.html", current_user=current_user)

@app.route("/register", methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        
        if username in load_users():
            flash("Username already exists! Please try a different one.", "danger")
        elif any(u['email'] == email for u in load_users().values()):
            flash("Email already registered! Do you want to login instead?", "danger")
        else:
            if add_user(username, email, password):
                user_data = get_user_by_username(username)
                user = User(user_data)
                login_user(user)
                flash("Registration successful!", "success")
                return render_template("register.html")
            else:
                flash("Registration failed. Please try again.", "danger")
    
    return render_template("register.html", current_user=current_user)

@app.route("/login", methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = load_users()
        user_data = users.get(username)
        
        if user_data and check_password_hash(user_data['password'], password):
            user_data['username'] = username
            user = User(user_data)
            login_user(user)
            
            # Update last login time
            update_user(username, {'last_login': datetime.now().isoformat()})
            
            flash("🔒 You're now securely logged in to your account.", "info")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash("Oops! Invalid username or password. Please try again.", "danger")
            flash("💡 Forgot your password? Click the link below to reset it.", "info")
    
    return render_template("login.html", current_user=current_user)

@app.route('/dashboard')
@login_required
def dashboard():
    stats = {
        'total_customers': len(dataset),
        'avg_age': round(dataset['Age'].mean(), 1),
        'most_common_profession': dataset['Profession'].mode()[0],
        'male_count': len(dataset[dataset['Gender'] == 'Male']),
        'female_count': len(dataset[dataset['Gender'] == 'Female']),
        'gender_distribution': dataset['Gender'].value_counts().to_dict()
    }
    return render_template("dashboard.html", stats=stats)

@app.route("/data_summary")
@login_required
def data_summary():
    summary = {
        'columns': list(dataset.columns),
        'missing_values': dataset.isnull().sum().to_dict(),
        'numeric_stats': dataset.describe().to_html(),
        'categorical_stats': dataset.describe(include=['O']).to_html()
    }
    return render_template("data_summary.html", summary=summary)

@app.route("/visualize", methods=['GET', 'POST'])
@login_required
def visualize_data():
    try:
        # Load the dataset
        dataset = pd.read_csv('Dataset/train.csv')

        # Apply filters if the request method is POST
        if request.method == 'POST':
            gender = request.form.get('gender')
            age_min = request.form.get('age_min')
            age_max = request.form.get('age_max')
            profession = request.form.get('profession')
            ever_married = request.form.get('ever_married')
            graduated = request.form.get('graduated')
            spending_score = request.form.get('spending_score')
            family_size = request.form.get('family_size')

            # Filter the dataset based on user input
            if gender:
                dataset = dataset[dataset['Gender'] == gender]
            if age_min:
                dataset = dataset[dataset['Age'] >= int(age_min)]
            if age_max:
                dataset = dataset[dataset['Age'] <= int(age_max)]
            if profession:
                dataset = dataset[dataset['Profession'] == profession]
            if ever_married:
                dataset = dataset[dataset['Ever_Married'] == ever_married]
            if graduated:
                dataset = dataset[dataset['Graduated'] == graduated]
            if spending_score:
                dataset = dataset[dataset['Spending_Score'] == spending_score]
            if family_size:
                dataset = dataset[dataset['Family_Size'] == int(family_size)]

        # Create visualizations dictionary
        plots = {}

        def fig_to_base64(fig):
            img = io.BytesIO()
            fig.savefig(img, format='png', bbox_inches='tight')
            img.seek(0)
            return base64.b64encode(img.getvalue()).decode('utf8')

        # 1. Gender Distribution
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.countplot(data=dataset, x='Gender', ax=ax)
        ax.set_title('Gender Distribution')
        plots['gender_distribution'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # 2. Age Distribution
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.histplot(data=dataset, x='Age', bins=20, kde=True, ax=ax)
        ax.set_title('Age Distribution')
        plots['age_distribution'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # 3. Marital Status Distribution
        fig, ax = plt.subplots(figsize=(8, 6))
        dataset['Ever_Married'].value_counts().plot.pie(autopct='%1.1f%%', ax=ax)
        ax.set_title('Marital Status Distribution')
        plots['marital_status'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # 4. Graduation Status
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.countplot(data=dataset, x='Graduated', ax=ax)
        ax.set_title('Graduation Status')
        plots['graduation_status'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # 5. Profession Distribution
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.countplot(data=dataset, y='Profession', order=dataset['Profession'].value_counts().index, ax=ax)
        ax.set_title('Profession Distribution')
        plots['profession_distribution'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # 6. Work Experience
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.boxplot(data=dataset, y='Work_Experience', ax=ax)
        ax.set_title('Work Experience Distribution')
        plots['work_experience'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # 7. Spending Score
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.countplot(data=dataset, x='Spending_Score', ax=ax)
        ax.set_title('Spending Score Distribution')
        plots['spending_score_dist'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # 8. Family Size
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.countplot(data=dataset, x='Family_Size', ax=ax)
        ax.set_title('Family Size Distribution')
        plots['family_size_dist'] = "data:image/png;base64," + fig_to_base64(fig)
        plt.close(fig)

        # Get unique values for dropdowns
        professions = sorted(dataset['Profession'].dropna().unique())
        spending_scores = sorted(dataset['Spending_Score'].dropna().unique())

        return render_template("visualize.html", plots=plots, professions=professions)

    except Exception as e:
        app.logger.error(f"Visualization error: {str(e)}", exc_info=True)
        flash(f"Error generating visualizations: {str(e)}", "danger")
        return redirect(url_for('dashboard'))
            
@app.route("/analyze", methods=['GET', 'POST'])
@login_required
def analyze_data():
    if request.method == 'POST':
        filters = {
            'genders': request.form.getlist('genders'),
            'age_range': [request.form.get('age_min'), request.form.get('age_max')],
            'professions': request.form.getlist('professions'),
            'marital_status': request.form.get('ever_married'),
            'graduated': request.form.get('graduated'),
            'spending_scores': request.form.getlist('spending_scores'),
            'family_size_range': [request.form.get('family_size_min'), request.form.get('family_size_max')],
            'search_query': request.form.get('search_query')
        }
        
        filtered_data = dataset.copy()
        
        # Apply filters
        if filters['genders']:
            filtered_data = filtered_data[filtered_data['Gender'].isin(filters['genders'])]
        if filters['age_range'][0]:
            filtered_data = filtered_data[filtered_data['Age'] >= float(filters['age_range'][0])]
        if filters['age_range'][1]:
            filtered_data = filtered_data[filtered_data['Age'] <= float(filters['age_range'][1])]
        if filters['professions']:
            filtered_data = filtered_data[filtered_data['Profession'].isin(filters['professions'])]
        if filters['marital_status']:
            filtered_data = filtered_data[filtered_data['Ever_Married'] == filters['marital_status']]
        if filters['graduated']:
            filtered_data = filtered_data[filtered_data['Graduated'] == filters['graduated']]
        if filters['spending_scores']:
            filtered_data = filtered_data[filtered_data['Spending_Score'].isin(filters['spending_scores'])]
        if filters['family_size_range'][0]:
            filtered_data = filtered_data[filtered_data['Family_Size'] >= float(filters['family_size_range'][0])]
        if filters['family_size_range'][1]:
            filtered_data = filtered_data[filtered_data['Family_Size'] <= float(filters['family_size_range'][1])]
        if filters['search_query']:
            query = filters['search_query'].lower()
            filtered_data = filtered_data[
                filtered_data.apply(lambda row: 
                    row.astype(str).str.lower().str.contains(query).any(), axis=1)
            ]
        
        # Save filtered data to session for export
        session['filtered_data'] = filtered_data.to_csv(index=False)
        
        return render_template("analysis_result.html",
                            data=filtered_data.to_html(classes='table table-striped'),
                            record_count=len(filtered_data),
                            filters=filters)
    
    professions = sorted(dataset['Profession'].dropna().unique())
    spending_scores = sorted(dataset['Spending_Score'].dropna().unique())
    return render_template("analyze.html", 
                         professions=professions,
                         spending_scores=spending_scores)

@app.route("/custom_visualization", methods=['GET', 'POST'])
@login_required
def custom_visualization():
    if request.method == 'POST':
        chart_type = request.form.get('chart_type')
        x_axis = request.form.get('x_axis')
        y_axis = request.form.get('y_axis')
        color_scheme = request.form.get('color_scheme')
        save_name = request.form.get('save_name')
        
        # Generate plot based on user selections
        plt.switch_backend('Agg')
        fig, ax = plt.subplots(figsize=(10, 6))
        
        try:
            # Define color palette mapping
            palette_map = {
                'viridis': 'viridis',
                'plasma': 'plasma',
                'magma': 'magma',
                'coolwarm': 'coolwarm',
                'Spectral': 'Spectral'
            }
            
            # Get the actual palette or default to 'viridis'
            palette = palette_map.get(color_scheme, 'viridis')
            
            if chart_type == 'bar':
                if not y_axis:
                    flash("Please select a Y-axis for bar chart", "danger")
                    return redirect(url_for('custom_visualization'))
                sns.barplot(data=dataset, x=x_axis, y=y_axis, ax=ax, palette=palette)
                ax.set_title(f"{y_axis} by {x_axis}")
            elif chart_type == 'scatter':
                if not y_axis:
                    flash("Please select a Y-axis for scatter plot", "danger")
                    return redirect(url_for('custom_visualization'))
                sns.scatterplot(data=dataset, x=x_axis, y=y_axis, ax=ax, palette=palette)
                ax.set_title(f"{y_axis} vs {x_axis}")
            elif chart_type == 'box':
                if not y_axis:
                    flash("Please select a Y-axis for box plot", "danger")
                    return redirect(url_for('custom_visualization'))
                sns.boxplot(data=dataset, x=x_axis, y=y_axis, ax=ax, palette=palette)
                ax.set_title(f"Distribution of {y_axis} by {x_axis}")
            elif chart_type == 'hist':
                # For histograms, use the first color from the palette
                hist_color = sns.color_palette(palette)[0]
                sns.histplot(data=dataset, x=x_axis, ax=ax, color=hist_color)
                ax.set_title(f"Distribution of {x_axis}")
            
            plt.tight_layout()
            
            # Save to buffer
            img = io.BytesIO()
            fig.savefig(img, format='png', bbox_inches='tight')
            img.seek(0)
            plot_url = base64.b64encode(img.getvalue()).decode('utf8')
            plt.close(fig)
            
            # Save to user preferences if name provided
            if save_name:
                conn = get_db_connection()
                try:
                    config = {
                        'chart_type': chart_type,
                        'x_axis': x_axis,
                        'y_axis': y_axis,
                        'color_scheme': color_scheme,
                        'plot_url': plot_url
                    }
                    
                    conn.execute('''
                        INSERT INTO user_visualizations (username, name, config)
                        VALUES (?, ?, ?)
                    ''', (current_user.id, save_name, json.dumps(config)))
                    conn.commit()
                    flash("Visualization saved successfully", "success")
                except Exception as e:
                    flash("Error saving visualization", "danger")
                    app.logger.error(f"Error saving visualization: {str(e)}")
                finally:
                    conn.close()
            
            return render_template("custom_visualization.html", 
                                plot_url=plot_url,
                                columns=dataset.columns,
                                saved_visualizations=get_user_visualizations(current_user.id))
        
        except Exception as e:
            if 'fig' in locals():
                plt.close(fig)
            flash(f"Error generating visualization: {str(e)}", "danger")
            app.logger.error(f"Visualization error: {str(e)}", exc_info=True)
            return redirect(url_for('custom_visualization'))
    
    return render_template("custom_visualization.html", 
                         columns=dataset.columns,
                         saved_visualizations=get_user_visualizations(current_user.id))

@app.route("/predict_spending", methods=['GET', 'POST'])
@login_required
def predict_spending():
    if request.method == 'POST':
        age = float(request.form.get('age'))
        work_experience = float(request.form.get('work_experience'))
        family_size = float(request.form.get('family_size'))
        
        # Simple prediction model (in a real app, use a trained ML model)
        if age < 30:
            prediction = "High" if work_experience > 3 else "Average"
        elif age < 50:
            prediction = "Average" if family_size > 3 else "High"
        else:
            prediction = "Low" if work_experience < 5 else "Average"
        
        return render_template("predict_spending.html",
                            prediction=prediction,
                            form_data=request.form)
    
    return render_template("predict_spending.html")

@app.route("/export_csv", methods=['POST'])
@login_required
def export_csv():
    filtered_data_csv = session.get('filtered_data', dataset.to_csv(index=False))
    return Response(
        filtered_data_csv,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=filtered_data.csv"}
    )

@app.route("/update_profile", methods=['GET', 'POST'])
@login_required
def update_profile():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        current_password = request.form['current_password']
        new_password = request.form.get('new_password')
        
        user_data = get_user_by_username(current_user.id)
        
        if not user_data or not check_password_hash(user_data['password'], current_password):
            flash("Current password is incorrect", "danger")
            return redirect(url_for('update_profile'))
        
        # Check if new username is available
        if username != current_user.id and username in load_users():
            flash("Username already taken", "danger")
            return redirect(url_for('update_profile'))
        
        # Check if new email is available
        if email != user_data['email'] and any(u['email'] == email for u in load_users().values()):
            flash("Email already in use", "danger")
            return redirect(url_for('update_profile'))
        
        # Update user info
        updates = {
            'username': username,
            'email': email
        }
        
        if new_password:
            updates['password'] = generate_password_hash(new_password)
        
        if update_user(current_user.id, updates):
            # Update current_user if username changed
            if username != current_user.id:
                user_data = get_user_by_username(username)
                user = User(user_data)
                login_user(user)
            
            flash("Profile updated successfully", "success")
            return redirect(url_for('profile_page'))
        else:
            flash("Failed to update profile", "danger")
            return redirect(url_for('update_profile'))
    
    user = get_user_by_username(current_user.id)
    return render_template("update_profile.html", user=user)

@app.route("/forgot_password", methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = get_user_by_email(email)
        
        if user:
            token = ts.dumps(email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            
            msg = Message("Password Reset Request",
                          recipients=[email])
            msg.body = f"Please click the link to reset your password: {reset_url}"
            
            try:
                mail.send(msg)
                flash("Password reset link sent to your email", "success")
            except Exception as e:
                flash("Failed to send reset email", "danger")
                app.logger.error(f"Email error: {str(e)}")
        else:
            flash("Email not found", "danger")
        
        return redirect(url_for('forgot_password'))
    
    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = ts.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash("The reset link is invalid or has expired", "danger")
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash("Passwords don't match", "danger")
            return redirect(request.url)
        
        conn = get_db_connection()
        hashed_password = generate_password_hash(password)
        conn.execute('UPDATE users SET password = ? WHERE email = ?', 
                    (hashed_password, email))
        conn.commit()
        conn.close()
        
        flash("Password updated successfully. Please login.", "success")
        return redirect(url_for('login_page'))
    
    return render_template("reset_password.html", token=token)

@app.route("/profile")
@login_required
def profile_page():
    user = get_user_by_username(current_user.id)
    return render_template("profile.html", user=user)

@app.route("/logout")
@login_required
def logout_page():
    logout_user()
    return redirect(url_for('home_page'))

# Chatbot API Endpoint
@app.route("/chatbot", methods=['POST'])
def chatbot():
    if not request.is_json:
        return jsonify({'success': False, 'reply': "I only understand JSON requests"})
    
    user_message = request.json.get('message', '').lower()
    username = current_user.id if current_user.is_authenticated else "Guest"
    
    # Enhanced response logic with more context
    responses = {
        'hello': [
            f"Hi {username}! How can I help you with customer segmentation today?",
            f"Hello {username}! What would you like to know about our data?"
        ],
        'help': [
            "I can help you with: <br>- Data visualizations 📊<br>- Customer analysis 🔍<br>- Exporting data 📁<br>What do you need?",
            "Try asking about:<br>- 'How to filter data'<br>- 'Show age distribution'<br>- 'Export customer data'"
        ],
        'visual': [
            "You can find visualizations under the <strong>Visualizations</strong> menu. Would you like me to take you there?",
            "We have charts showing:<br>- Customer demographics 👨‍👩‍👧‍👦<br>- Spending patterns 💰<br>- Professional distributions 👔"
        ],
        'analyze': [
            "The <strong>Analyze Data</strong> section lets you filter by:<br>- Age range<br>- Profession<br>- Spending score<br>- Family size",
            "You can export filtered data as CSV from the analysis page. Need help with specific filters?"
        ],
        'feedback': [
            "You can submit feedback through the <strong>Feedback</strong> page in your profile menu.",
            "We appreciate your feedback! You'll find the feedback option in the navigation bar."
        ],
        'default': [
            "I'm still learning about customer segmentation. Could you try asking differently?",
            "I'm not sure I understand. Try asking about visualizations, data analysis, or customer segments."
        ]
    }
    
    # Determine response category
    if any(greet in user_message for greet in ['hello', 'hi', 'hey']):
        reply = random.choice(responses['hello'])
    elif 'help' in user_message:
        reply = random.choice(responses['help'])
    elif any(visual_word in user_message for visual_word in ['visual', 'graph', 'chart', 'plot']):
        reply = random.choice(responses['visual'])
    elif any(analyze_word in user_message for analyze_word in ['analyze', 'filter', 'data', 'segment']):
        reply = random.choice(responses['analyze'])
    elif 'feedback' in user_message or 'suggest' in user_message:
        reply = random.choice(responses['feedback'])
    else:
        reply = random.choice(responses['default'])
    
    return jsonify({'success': True, 'reply': reply})

# Feedback Routes
@app.route("/feedback")
@login_required
def feedback_page():
    return render_template("feedback.html")

@app.route("/submit_feedback", methods=['POST'])
@login_required
def submit_feedback():
    feedback_text = request.json.get('feedback', '').strip()
    
    if not feedback_text:
        return jsonify({'success': False, 'message': 'Feedback cannot be empty'})
    
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO feedback (username, feedback) 
            VALUES (?, ?)
        ''', (current_user.id, feedback_text))
        conn.commit()
        conn.close()
        
        # Log the feedback (optional)
        app.logger.info(f"New feedback submitted by {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Thank you for your feedback! We appreciate your input.'
        })
    except Exception as e:
        app.logger.error(f"Feedback submission error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while submitting your feedback. Please try again.'
        })
        
@app.route("/view_feedback")
@login_required
def view_feedback():
    conn = get_db_connection()
    feedback_data = conn.execute('''
        SELECT username, feedback, timestamp 
        FROM feedback 
        ORDER BY timestamp DESC
    ''').fetchall()
    conn.close()
    return render_template("view_feedback.html", feedback_data=feedback_data)

if __name__ == "__main__":
    app.run(debug=True)