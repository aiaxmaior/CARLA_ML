import pygame
import time
import sys

# --- Pygame Setup ---
pygame.init()
pygame.joystick.init()

joystick_count = pygame.joystick.get_count()

if joystick_count == 0:
    print("Error: No joysticks found. Please connect your Fanatec wheel kit.")
    pygame.quit()
    sys.exit()

print(f"Found {joystick_count} joystick(s):")

joysticks = []
for i in range(joystick_count):
    try:
        joystick = pygame.joystick.Joystick(i)
        joystick.init()
        joysticks.append(joystick)
        print(f"  Joystick {i}: {joystick.get_name()}")
        print(f"    Axes: {joystick.get_numaxes()}, Buttons: {joystick.get_numbuttons()}, Hats: {joystick.get_numhats()}")
    except pygame.error as e:
        print(f"  Error initializing joystick {i}: {e}")
        # Continue to the next joystick if one fails

if not joysticks:
    print("Error: No joysticks could be successfully initialized.")
    pygame.quit()
    sys.exit()


print("\nInstructions:")
print("1. Interact with your wheel, pedals, buttons, and D-pads one at a time.")
print("2. Observe the output below to identify which joystick index and which control index corresponds to each physical input.")
print("   - Axes will show floating-point values (e.g., A0:0.5000)")
print("   - Buttons will show 0 (released) or 1 (pressed) (e.g., B5:1)")
print("   - Hats (D-pads) will show a tuple indicating direction (e.g., H0:(0, 1) for Up)")
print("Press Ctrl+C in the terminal to exit.")

# --- Real-time Input Reading Loop ---
try:
    while True:
        # Process Pygame events to keep the window responsive and detect quit events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt # Exit loop if window is closed (unlikely here)

        # Read and print input states for ALL initialized joysticks
        all_input_data = []
        for i, joystick in enumerate(joysticks):
            joystick_data_parts = [] # Use a list to collect formatted parts for this joystick
            try:
                # --- Read Axes ---
                num_axes = joystick.get_numaxes()
                if num_axes > 0:
                    axis_values = [joystick.get_axis(j) for j in range(num_axes)]
                    # Format the axis values with axis number labels and .4f precision
                    formatted_axes = [f"A{j}:{axis_values[j]:.4f}" for j in range(num_axes)]
                    joystick_data_parts.append(f"Axes: [{', '.join(formatted_axes)}]")

                # --- Read Buttons ---
                num_buttons = joystick.get_numbuttons()
                if num_buttons > 0:
                    button_values = [joystick.get_button(j) for j in range(num_buttons)]
                    # Format button values with button number labels (0 or 1)
                    formatted_buttons = [f"B{j}:{button_values[j]}" for j in range(num_buttons)]
                    joystick_data_parts.append(f"Buttons: [{', '.join(formatted_buttons)}]")

                # --- Read Hats ---
                num_hats = joystick.get_numhats()
                if num_hats > 0:
                    hat_values = [joystick.get_hat(j) for j in range(num_hats)]
                    # Format hat values with hat number labels (tuple)
                    formatted_hats = [f"H{j}:{hat_values[j]}" for j in range(num_hats)]
                    joystick_data_parts.append(f"Hats: [{', '.join(formatted_hats)}]")

                # Combine data for this joystick
                if joystick_data_parts:
                     all_input_data.append(f"J{i} | {' | '.join(joystick_data_parts)}")
                else:
                     all_input_data.append(f"J{i} | No input data (Axes, Buttons, Hats) detected")


            except pygame.error as e:
                # Handle potential errors during reading
                all_input_data.append(f"J{i} | Error reading input: {e}")

        # Join data from all joysticks and print on a single line
        if all_input_data:
             print(" | ".join(all_input_data), end='\r')
        else:
             print("No active joystick data to display.", end='\r')


        # Small delay to control the loop speed
        time.sleep(0.01) # Adjust as needed

except KeyboardInterrupt:
    # This block is executed when the user presses Ctrl+C
    print("\nExiting script.")
except Exceaption as e:
    # Catch any other unexpected errors
    print(f"\nAn unexpected error occurred: {e}")

finally:
    # --- Clean up ---
    pygame.joystick.quit()
    pygame.quit()
    print("Pygame quit.")