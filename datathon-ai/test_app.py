# test_app.py - Let's test if this works!
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def hello():
    return "<h1 style='color: red; font-size: 50px;'>🎉 IT WORKS! 🎉</h1>"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)