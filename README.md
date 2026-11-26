SignBridge is a sign-language learning website built with Flask, SQLite and Google MediaPipe. It uses the webcam to track the user's hand in real time and checks whether they are making the correct sign.

Features

Login: users register and sign in to their own account.
Learn: cards for each sign, with hand-shape drawings to show how it looks.
Admin recording: the admin records sign samples with the webcam, which become the data the app recognises.
Practice: the user shows a sign to the camera and the app recognises it live.
Quiz: a timed game of up to 10 signs, 15 seconds each. A correct sign scores 10 points plus 1 point for every second left.
Translator: converts signs shown to the camera into text.
Dashboard: shows the user's quiz results and progress.

How it works
MediaPipe finds 21 landmark points on the hand. The app normalises these points and compares them with the admin's recorded samples. The closest match under a set threshold is the recognised sign. The app smooths the result over several frames to avoid flickering.

Tech stack

Backend: Python, Flask
Database: SQLite
Frontend: HTML, CSS, JavaScript (Jinja templates)
Hand tracking: MediaPipe Hand Landmarker

Run locally

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py

Then open http://127.0.0.1:5000.

Check the Translator and Dashboard lines against what your pages actually do, and change them if they differ. Also make sure requirements.txt exists. If not, run pip freeze > requirements.txt in the terminal first.
