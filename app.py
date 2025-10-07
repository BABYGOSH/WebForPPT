from flask import Flask, render_template, request, redirect, url_for, send_from_directory # pyright: ignore[reportMissingImports]
import os

app = Flask(__name__)
import os
print("Template folder:", os.path.join(os.getcwd(), "templates"))
import os
print("📂 Flask template folder path:", os.path.join(os.getcwd(), "templates"))
print("📄 Files inside templates:", os.listdir(os.path.join(os.getcwd(), "templates")))

# Folder to store uploaded PowerPoint files
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Make sure the folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Home page: show all uploaded slides
@app.route('/')
def home():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', files=files)

# Upload new file
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
    return redirect(url_for('home'))

# Download file
@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
