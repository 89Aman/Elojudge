
import pandas as pd
from sklearn.linear_model import LinearRegression

# Create dataset
data = {
    'Area': [1000, 1500, 2000, 2500, 3000],
    'Bedrooms': [2, 3, 3, 4, 4],
    'Servant_Room': [0, 0, 1, 1, 1],
    'Price': [20, 30, 40, 50, 60]
}

df = pd.DataFrame(data)

# Select input and output
X = df[['Area', 'Bedrooms', 'Servant_Room']]
y = df['Price']

# Create and train model
model = LinearRegression()
model.fit(X, y)

# Predict house price
new_house = [[1800, 3, 1]]
prediction = model.predict(new_house)

print("Area: 1800 sq.ft")
print("Bedrooms: 3")
print("Servant Room: Yes")
print("Predicted Price:", prediction[0], "Lakhs")
