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
        all_joystick_data = []
        for i, joystick in enumerate(joysticks):
            axis_values = [joystick.get_axis(j) for j in range(joystick.get_numaxes())]
            button_values = [joystick.get_button(j) for j in range(joystick.get_numbuttons())]
            hat_values = [joystick.get_hat(j) for j in range(joystick.get_numhats())]

            axes_str = f"Axes:[{', '.join([f'{v:.2f}' for v in axis_values])}]"
            buttons_str = f"Btns:[{', '.join([str(v) for v in button_values])}]"
            # Hat values are tuples (x, y), so format them nicely
            hats_str = f"Hats:[{', '.join([f'({h[0]},{h[1]})' for h in hat_values])}]"

            joystick_info = f"J{i} {axes_str} {buttons_str} {hats_str}"
            all_joystick_data.append(joystick_info)

        # Clear the line with spaces first to avoid leftover characters if the new line is shorter
        print(" " * 150, end='\r') # Adjust width as needed
        print(" | ".join(all_joystick_data), end='\r')

        time.sleep(0.01) # Small delay to avoid overwhelming the console

except KeyboardInterrupt:
    print("\nExiting.")
finally:
    pygame.quit()