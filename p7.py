
import pandas as pd
from sklearn.linear_model import LogisticRegression

# Create dataset
data = {
    'Attendance': [90, 80, 60, 70, 95, 50, 85, 40],
    'Marks': [85, 75, 50, 60, 90, 45, 80, 30],
    'Interest': [1, 1, 0, 1, 1, 0, 1, 0],
    'Suitable': [1, 1, 0, 0, 1, 0, 1, 0]
}

df = pd.DataFrame(data)

# Input and output
X = df[['Attendance', 'Marks', 'Interest']]
y = df['Suitable']

# Create model
model = LogisticRegression()

# Train model
model.fit(X, y)

# Predict for a new student
student = [[85, 80, 1]]
prediction = model.predict(student)

if prediction[0] == 1:
    print("Student is Suitable for the Activity")
else:
    print("Student is Not Suitable for the Activity")
