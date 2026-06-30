from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <h1>Hej!</h1>
    <p>To moja pierwsza aplikacja na Renderze 🚀</p>
    """

if __name__ == "__main__":
    app.run(debug=True)