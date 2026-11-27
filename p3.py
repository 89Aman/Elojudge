
# Conditional Statement
num = 10

if num > 0:
    print("Number is Positive")
else:
    print("Number is Negative")

# For Loop
print("\nFor Loop:")
for i in range(1, 6):
    print(i)

# While Loop
print("\nWhile Loop:")
i = 1
while i <= 5:
    print(i)
    i += 1

# Break Statement
print("\nBreak Statement:")
for i in range(1, 6):
    if i == 4:
        break
    print(i)

# Continue Statement
print("\nContinue Statement:")
for i in range(1, 6):
    if i == 3:
        continue
    print(i)
