import pygame
import time
import sys
import os # Import os to potentially clear the screen

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

# Function to clear the terminal screen (optional, makes multi-line output cleaner)
def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

# --- Real-time Input Reading Loop ---
try:
    while True:
        # Process Pygame events to keep the window responsive and detect quit events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt # Exit loop if window is closed (unlikely here)

        # Optional: Uncomment the line below to clear the screen before each update.
        # This provides a cleaner multi-line output but may cause flickering.
        # clear_screen()
        # print("--- Joystick States ---") # Optional header if clearing screen

        # Read and print input states for ALL initialized joysticks
        for i, joystick in enumerate(joysticks):
            print(f"J{i}:\n") # Print joystick index on its own line
            try:
                # --- Read Axes ---
                num_axes = joystick.get_numaxes()
                if num_axes > 0:
                    axis_values = [joystick.get_axis(j) for j in range(num_axes)]
                    # Format the axis values with axis number labels and .4f precision
                    formatted_axes = [f"A{j}:\n     {axis_values[j]:.4f}\n" for j in range(num_axes)]
                    print(f"    Axes: [{', '.join(formatted_axes)}]\n") # Print axes on a new indented line

                # --- Read Buttons ---
                num_buttons = joystick.get_numbuttons()
                if num_buttons > 0:
                    button_values = [joystick.get_button(j) for j in range(num_buttons)]
                    # Format button values with button number labels (0 or 1)
                    formatted_buttons = [f"B{j}:     {button_values[j]}" for j in range(num_buttons)]
                    print(f"    Buttons: [{', '.join(formatted_buttons)}]") # Print buttons on a new indented line

                # --- Read Hats ---
                num_hats = joystick.get_numhats()
                if num_hats > 0:
                    hat_values = [joystick.get_hat(j) for j in range(num_hats)]
                    # Format hat values with hat number labels (tuple)
                    formatted_hats = [f"H{j}:\n     {hat_values[j]}" for j in range(num_hats)]
                    print(f"    Hats:\n [{', '.join(formatted_hats)}]\n") # Print hats on a new indented line

                if num_axes == 0 and num_buttons == 0 and num_hats == 0:
                     print("    No input data (Axes, Buttons, Hats) detected for this joystick.")

            except pygame.error as e:
                # Handle potential errors during reading - this print adds a newline
                print(f"    Error reading input: {e}")

            print("-" * 20) # Separator line for clarity between joysticks

        # Small delay to control the loop speed
        time.sleep(5) # Increased delay slightly for better readability with multi-line output

except KeyboardInterrupt:
    # This block is executed when the user presses Ctrl+C
    print("\nExiting script.")
except Exception as e:
    # Catch any other unexpected errors
    print(f"\nAn unexpected error occurred: {e}")

finally:
    # --- Clean up ---
    pygame.joystick.quit()
    pygame.quit()
    print("Pygame quit.")