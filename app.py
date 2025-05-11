from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_bootstrap import Bootstrap5
import sqlite3
import os
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_premium_secret_key_here'
bootstrap = Bootstrap5(app)

# Configuration
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Simple database initialization
def init_db():
    conn = sqlite3.connect('jewelry.db')
    c = conn.cursor()
    
    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS jewelry
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 name TEXT NOT NULL,
                 description TEXT,
                 price REAL NOT NULL,
                 carat REAL,
                 category TEXT,
                 image_url TEXT,
                 is_featured BOOLEAN DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE NOT NULL,
                 password TEXT NOT NULL)''')
    
    # Insert admin user if not exists
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                 ('admin', 'admin123'))
    except sqlite3.IntegrityError:
        pass
    
    conn.commit()
    conn.close()

init_db()

# Admin decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session['username'] != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    sort_by = request.args.get('sort', 'price_asc')
    category = request.args.get('category', 'all')
    
    conn = sqlite3.connect('jewelry.db')
    c = conn.cursor()
    
    # Base query
    query = "SELECT * FROM jewelry"
    
    # Filter by category
    if category != 'all':
        query += f" WHERE category = '{category}'"
    
    # Sorting
    if sort_by == 'price_asc':
        query += " ORDER BY price ASC"
    elif sort_by == 'price_desc':
        query += " ORDER BY price DESC"
    elif sort_by == 'carat_asc':
        query += " ORDER BY carat ASC"
    elif sort_by == 'carat_desc':
        query += " ORDER BY carat DESC"
    
    c.execute(query)
    jewelry_items = c.fetchall()
    
    # Get categories for filter
    c.execute("SELECT DISTINCT category FROM jewelry WHERE category IS NOT NULL")
    categories = [cat[0] for cat in c.fetchall()]
    
    conn.close()
    
    # Get cart count for badge
    cart_count = len(session.get('cart', []))
    favorites = session.get('favorites', [])
    
    return render_template('index.html', 
                         jewelry=jewelry_items, 
                         categories=categories,
                         cart_count=cart_count,
                         favorites=favorites,
                         current_sort=sort_by,
                         current_category=category)

@app.route('/add_to_cart/<int:item_id>')
def add_to_cart(item_id):
    if 'cart' not in session:
        session['cart'] = []
    
    if item_id not in session['cart']:
        session['cart'].append(item_id)
        session.modified = True
        flash('Item added to cart', 'success')
    else:
        flash('Item already in cart', 'info')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/remove_from_cart/<int:item_id>')
def remove_from_cart(item_id):
    if 'cart' in session and item_id in session['cart']:
        session['cart'].remove(item_id)
        session.modified = True
        flash('Item removed from cart', 'success')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/toggle_favorite/<int:item_id>')
def toggle_favorite(item_id):
    if 'favorites' not in session:
        session['favorites'] = []
    
    if item_id in session['favorites']:
        session['favorites'].remove(item_id)
    else:
        session['favorites'].append(item_id)
    
    session.modified = True
    return redirect(request.referrer or url_for('index'))

@app.route('/cart')
def view_cart():
    if 'cart' not in session or not session['cart']:
        return render_template('cart.html', items=[], total=0)
    
    conn = sqlite3.connect('jewelry.db')
    c = conn.cursor()
    
    # Use parameterized query to prevent SQL injection
    placeholders = ','.join(['?']*len(session['cart']))
    query = f"SELECT * FROM jewelry WHERE id IN ({placeholders})"
    c.execute(query, session['cart'])
    
    items = c.fetchall()
    total = sum(item[3] for item in items)  # Sum of prices
    
    conn.close()
    
    return render_template('cart.html', items=items, total=total)

@app.route('/favorites')
def view_favorites():
    if 'favorites' not in session or not session['favorites']:
        return render_template('favorites.html', items=[])
    
    conn = sqlite3.connect('jewelry.db')
    c = conn.cursor()
    
    placeholders = ','.join(['?']*len(session['favorites']))
    query = f"SELECT * FROM jewelry WHERE id IN ({placeholders})"
    c.execute(query, session['favorites'])
    
    items = c.fetchall()
    conn.close()
    
    return render_template('favorites.html', items=items)

# Admin routes
@app.route('/admin')
@admin_required
def admin():
    conn = sqlite3.connect('jewelry.db')
    c = conn.cursor()
    c.execute("SELECT * FROM jewelry")
    items = c.fetchall()
    conn.close()
    return render_template('admin.html', jewelry=items)

@app.route('/admin/add', methods=['GET', 'POST'])
@admin_required
def add_item():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        carat = float(request.form['carat']) if request.form['carat'] else None
        category = request.form['category']
        image_url = request.form['image_url']
        is_featured = 'is_featured' in request.form
        
        conn = sqlite3.connect('jewelry.db')
        c = conn.cursor()
        c.execute('''INSERT INTO jewelry 
                    (name, description, price, carat, category, image_url, is_featured)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (name, description, price, carat, category, image_url, is_featured))
        conn.commit()
        conn.close()
        
        flash('Jewelry item added successfully', 'success')
        return redirect(url_for('admin'))
    
    return render_template('add_item.html')

@app.route('/admin/edit/<int:item_id>', methods=['GET', 'POST'])
@admin_required
def edit_item(item_id):
    conn = sqlite3.connect('jewelry.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        carat = float(request.form['carat']) if request.form['carat'] else None
        category = request.form['category']
        image_url = request.form['image_url']
        is_featured = 'is_featured' in request.form
        
        c.execute('''UPDATE jewelry SET 
                    name=?, description=?, price=?, carat=?, category=?, image_url=?, is_featured=?
                    WHERE id=?''',
                 (name, description, price, carat, category, image_url, is_featured, item_id))
        conn.commit()
        conn.close()
        
        flash('Jewelry item updated successfully', 'success')
        return redirect(url_for('admin'))
    
    c.execute("SELECT * FROM jewelry WHERE id=?", (item_id,))
    item = c.fetchone()
    conn.close()
    
    if not item:
        flash('Item not found', 'danger')
        return redirect(url_for('admin'))
    
    return render_template('edit_item.html', item=item)

@app.route('/admin/delete/<int:item_id>')
@admin_required
def delete_item(item_id):
    conn = sqlite3.connect('jewelry.db')
    c = conn.cursor()
    c.execute("DELETE FROM jewelry WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    
    # Remove from carts and favorites if present
    if 'cart' in session and item_id in session['cart']:
        session['cart'].remove(item_id)
    if 'favorites' in session and item_id in session['favorites']:
        session['favorites'].remove(item_id)
    session.modified = True
    
    flash('Jewelry item deleted successfully', 'success')
    return redirect(url_for('admin'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('jewelry.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            session['username'] = username
            flash('Logged in successfully', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
