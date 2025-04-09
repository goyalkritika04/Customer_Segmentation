import os
import sqlite3
import random
from flask import Flask, render_template, request, flash, redirect, url_for, Response, jsonify
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET_KEY', 'your_default_secret_key')

# Load and prepare dataset
dataset = pd.read_csv('Dataset/train.csv')

# Data cleaning
dataset['Profession'] = dataset['Profession'].fillna('Unknown')
dataset['Gender'] = dataset['Gender'].fillna('Unknown')
if 'Spending_Score' in dataset.columns:
    dataset['Spending_Score'] = dataset['Spending_Score'].fillna('Unknown')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"

class User(UserMixin):
    pass

@login_manager.user_loader
def user_loader(username):
    user = get_user_by_username(username)
    if user:
        user_obj = User()
        user_obj.id = username
        return user_obj
    return None

def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def create_user_table():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            feedback TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    ''')
    conn.commit()
    conn.close()

def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user

def add_user(username, email, password):
    hashed_password = generate_password_hash(password)
    conn = get_db_connection()
    conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', 
                (username, email, hashed_password))
    conn.commit()
    conn.close()

@app.route("/")
def home_page():
    return render_template("home.html", current_user=current_user)

@app.route("/register", methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        
        if get_user_by_username(username):
            flash("Username already exists!", "danger")
        else:
            add_user(username, email, password)
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login_page'))
    
    return render_template("register.html", current_user=current_user)

@app.route("/login", methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user_by_username(username)
        
        if user and check_password_hash(user['password'], password):
            user_obj = User()
            user_obj.id = username
            login_user(user_obj)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash("Invalid username or password!", "danger")
    
    return render_template("login.html", current_user=current_user)

@app.route('/dashboard')
@login_required
def dashboard():
    stats = {
        'total_customers': len(dataset),
        'avg_age': round(dataset['Age'].mean(), 1),
        'most_common_profession': dataset['Profession'].mode()[0],
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
        # Set the backend to Agg (non-interactive) before importing pyplot
        import matplotlib
        matplotlib.use('Agg')  # Set the backend to Agg
        import matplotlib.pyplot as plt
        import seaborn as sns
        
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
            
@app.route("/analyse", methods=['GET', 'POST'])
@login_required
def analyze_data():
    if request.method == 'POST':
        filters = {
            'gender': request.form.get('gender'),
            'age_min': request.form.get('age_min'),
            'age_max': request.form.get('age_max'),
            'profession': request.form.get('profession'),
            'ever_married': request.form.get('ever_married'),
            'graduated': request.form.get('graduated'),
            'spending_score': request.form.get('spending_score'),
            'family_size_min': request.form.get('family_size_min'),
            'family_size_max': request.form.get('family_size_max')
        }
        
        filtered_data = dataset.copy()
        
        # Apply filters
        if filters['gender']:
            filtered_data = filtered_data[filtered_data['Gender'] == filters['gender']]
        if filters['age_min']:
            filtered_data = filtered_data[filtered_data['Age'] >= float(filters['age_min'])]
        if filters['age_max']:
            filtered_data = filtered_data[filtered_data['Age'] <= float(filters['age_max'])]
        if filters['profession']:
            filtered_data = filtered_data[filtered_data['Profession'] == filters['profession']]
        
        return render_template("analysis_result.html",
                            data=filtered_data.to_html(classes='table table-striped'),
                            record_count=len(filtered_data),
                            filters={k: v for k, v in filters.items() if v})  # Only pass non-empty filters
    
    professions = sorted(dataset['Profession'].unique())
    spending_scores = sorted(dataset['Spending_Score'].dropna().unique())
    return render_template("analyse.html", 
                         professions=professions,
                         spending_scores=spending_scores)
    
@app.route("/export_csv", methods=['POST'])
@login_required
def export_csv():
        app.logger.info(f"Received filters: {request.form.to_dict()}")
        filters = request.form.to_dict()
        filtered_data = dataset.copy()
    
        if filters.get('gender'):
            filtered_data = filtered_data[filtered_data['Gender'] == filters['gender']]
        if filters.get('age_min'):
            filtered_data = filtered_data[filtered_data['Age'] >= float(filters['age_min'])]
        if filters.get('age_max'):
            filtered_data = filtered_data[filtered_data['Age'] <= float(filters['age_max'])]
        if filters.get('profession'):
            filtered_data = filtered_data[filtered_data['Profession'] == filters['profession']]
        
        output = StringIO()
        filtered_data.to_csv(output, index=False)
        output.seek(0)
        return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=filtered_data.csv"}
    )

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
        
        # Insert feedback
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

if __name__ == "__main__":
    create_user_table()
    app.run(debug=True)