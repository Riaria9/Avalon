#### Install dependencies

- For Python, run `pip install -r requirements.txt`, I’d strongly suggest creating a virtual environment for that
- For node.js, run `npm install`

#### Run the program

- Start frontend and backend together, run `npm start`, which runs both `uvicorn --app-dir=./backend test:app --reload` and `wait-on http://localhost:8000 && react-scripts start` concurrently as specified in package.json