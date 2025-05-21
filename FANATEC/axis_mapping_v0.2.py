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

# --- IMPORTANT: Replace these placeholders with your actual joystick and control IDs! ---
# Use the output from the joystick_input_finder.py script to find these values.

# Steering
STEER_JOYSTICK_ID = 1
STEER_AXIS_ID = 0

# Throttle
THROTTLE_JOYSTICK_ID = 1
THROTTLE_AXIS_ID = 1

# Brake
BRAKE_JOYSTICK_ID = 1
BRAKE_AXIS_ID = 5

# --- Helper function for pedal mapping (handles inversion and 0-1 range) ---
def map_pedal_input(raw_value):
    """
    Maps raw pedal axis value to CARLA's throttle/brake range (0.0 to 1.0).
    Assumes raw_value is -1 (pressed) to 1 (released) and inverts it.
    """
    # Pygame output is often -1 (pressed) to 1 (released) for pedals
    # We want 0 (released) to 1 (pressed) for CARLA
    # Invert the value, then scale from -1..1 to 0..2, then divide by 2
    return (raw_value * -1 + 1) / 2

# --- Helper function for steering mapping ---
def map_steering_input(raw_value):
    """
    Maps raw steering axis value to CARLA's steer range (-1.0 to 1.0).
    Assumes raw_value is already -1.0 (left) to 1.0 (right).
    """
    # Assuming raw_value is already -1.0 (left) to 1.0 (right)
    # Add deadzone or non-linearity here if needed
    return raw_value


print("\nReading configured inputs. Press Ctrl+C to exit.")
# print("Press Ctrl+C to exit.") # Removed redundant print

# --- Real-time Input Reading Loop ---
try:
    while True:
        # Process events to keep Pygame responsive
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt # Use exception to break loop
            # Add handling for button/hat events here if needed to update control state

        # Initialize control values
        steer_val = 0.0
        throttle_val = 0.0
        brake_val = 0.0
        # Add other control variables (handbrake, gear, etc.) initialized to default states

        # Read Steering
        # Check if the joystick and axis IDs are valid before attempting to read
        if STEER_JOYSTICK_ID < joystick_count and joysticks[STEER_JOYSTICK_ID].get_numaxes() > STEER_AXIS_ID:
            raw_steer = joysticks[STEER_JOYSTICK_ID].get_axis(STEER_AXIS_ID)
            steer_val = map_steering_input(raw_steer)
        # Removed the else block with sys.stdout.write to prevent newlines

        # Read Throttle
        # Check if the joystick and axis IDs are valid before attempting to read
        if THROTTLE_JOYSTICK_ID < joystick_count and joysticks[THROTTLE_JOYSTICK_ID].get_numaxes() > THROTTLE_AXIS_ID:
            raw_throttle = joysticks[THROTTLE_JOYSTICK_ID].get_axis(THROTTLE_AXIS_ID)
            throttle_val = map_pedal_input(raw_throttle)
        # Removed the else block with sys.stdout.write to prevent newlines

        # Read Brake
        # Check if the joystick and axis IDs are valid before attempting to read
        if BRAKE_JOYSTICK_ID < joystick_count and joysticks[BRAKE_JOYSTICK_ID].get_numaxes() > BRAKE_AXIS_ID:
            raw_brake = joysticks[BRAKE_JOYSTICK_ID].get_axis(BRAKE_AXIS_ID)
            brake_val = map_pedal_input(raw_brake)
        # Removed the else block with sys.stdout.write to prevent newlines

        # --- Now, steer_val, throttle_val, brake_val hold the latest mapped inputs ---
        # These values would be used to create and apply the carla.VehicleControl object.
        # Example (CARLA connection and vehicle object assumed to exist):
        # carla_control = carla.VehicleControl(
        #     throttle=float(throttle_val),
        #     steer=float(steer_val),
        #     brake=float(brake_val),
        #     # Add other parameters based on button/hat states
        #     hand_brake=False,
        #     reverse=False,
        #     manual_gear_shift=False,
        #     gear=1
        # )
        # vehicle.apply_control(carla_control)
        # world.tick() # If in synchronous mode

        # --- Print the current state on a single line ---
        output_string = f"Steer: {steer_val:+.2f} | Throttle: {throttle_val:.2f} | Brake: {brake_val:.2f}"
        # Add other control values to the output_string as you map them

        # Clear the previous line with spaces and then write the new data
        # Using a fixed number of spaces is a simple way to clear
        # A more robust way might involve getting terminal width, but this is usually sufficient
        sys.stdout.write(" " * 80 + '\r') # Write enough spaces to clear the longest possible line
        sys.stdout.write(output_string + '\r') # Write the new data, ending with carriage return
        sys.stdout.flush() # Ensure the output is immediately written to the console

        # Small delay to control the loop speed (adjust as needed)
        # This script is just for testing input reading frequency, not tied to CARLA tick yet
        time.sleep(0.001) # Example: Read input at 1000 Hz (1ms interval)

except KeyboardInterrupt:
    print("\nExiting.") # Print a newline before the exit message
except Exception as e:
    print(f"\nAn unexpected error occurred: {e}") # Print a newline before the error message

finally:
    # --- Clean up ---
    pygame.quit()
    print("Pygame quit.")

