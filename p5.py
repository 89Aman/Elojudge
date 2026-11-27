
import numpy as np
from sklearn.linear_model import LinearRegression

# Dataset (Area in sq. ft.)
area = np.array([[1000], [1500], [2000], [2500], [3000]])

# House prices (in lakhs)
price = np.array([20, 30, 40, 50, 60])

# Create Linear Regression model
model = LinearRegression()

# Train the model
model.fit(area, price)

# Predict price for a new house
new_area = np.array([[1800]])
predicted_price = model.predict(new_area)

print("House Area:", new_area[0][0], "sq. ft.")
print("Predicted House Price:", predicted_price[0], "Lakhs")
