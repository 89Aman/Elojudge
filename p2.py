
import numpy as np
import matplotlib.pyplot as plt

# Create matrix data
data = np.array([
    [1, 10],
    [2, 20],
    [3, 30],
    [4, 40],
    [5, 50]
])

# Extract X and Y values
x = data[:, 0]
y = data[:, 1]

# Plot graph
plt.plot(x, y, marker='o', label='Data Values')

# Add labels
plt.xlabel("X-Axis")
plt.ylabel("Y-Axis")
plt.title("Graph Based on Matrix Data")

# Display data labels
for i in range(len(x)):
    plt.text(x[i], y[i], str(y[i]))

plt.legend()
plt.grid()
plt.show()
