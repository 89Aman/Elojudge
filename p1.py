
import numpy as np

# Create two matrices
A = np.array([[1, 2], [3, 4]])
B = np.array([[5, 6], [7, 8]])

print("Matrix A:")
print(A)

print("Matrix B:")
print(B)

# Addition
print("Addition:")
print(A + B)

# Subtraction
print("Subtraction:")
print(A - B)

# Multiplication
print("Multiplication:")
print(np.dot(A, B))

# Display specific row
print("First Row of Matrix A:")
print(A[0, :])

# Display specific column
print("First Column of Matrix A:")
print(A[:, 0])
