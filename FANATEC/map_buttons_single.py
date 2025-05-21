import pygame
import time

pygame.init()
pygame.joystick.init()

joystick_count = pygame.joystick.get_count()
if joystick_count == 0:
    print("No joysticks found.")
    pygame.quit()
    exit()

print(f"Found {joystick_count} joysticks:")

joysticks = []
for i in range(joystick_count):
    joystick = pygame.joystick.Joystick(i)
    joystick.init()
    joysticks.append(joystick)
    print(f"  Joystick {i}: {joystick.get_name()} (Axes: {joystick.get_numaxes()}, Buttons: {joystick.get_numbuttons()}, Hats: {joystick.get_numhats()})")


print("\nMove your pedals (throttle, brake, clutch) one at a time.")
print("Observe which joystick index and axis value changes significantly.")
print("Press Ctrl+C to exit.")

try:
    while True:
        # Process events to keep Pygame responsive
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt # Use exception to break loop

        # Read and print axis values for ALL joysticks
        all_axes_data = []
        for i, joystick in enumerate(joysticks):
            axis_values = [joystick.get_axis(j) for j in range(joystick.get_numaxes())]
            all_axes_data.append(f"J{i} Axes: [{', '.join([f'{v:.4f}' for v in axis_values])}]")

        print(" | ".join(all_axes_data), end='\r') # Print on the same line for all joysticks

        time.sleep(0.01) # Small delay to avoid overwhelming the console

except KeyboardInterrupt:
    print("\nExiting.")
finally:
    pygame.quit()