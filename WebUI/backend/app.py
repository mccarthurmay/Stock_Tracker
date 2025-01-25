from flask import Flask, jsonify
from flask_cors import CORS
from analysis import showinfo  # Import the function from script1




app = Flask(__name__)
CORS(app)
# Define an endpoint to call the Python functions
@app.route('/analysis', methods=['GET'])
def run_script1():
    result = showinfo("GOOG")  # Call the function from script1.py
    return jsonify({'result': result})


if __name__ == '__main__':
    app.run(debug=True)