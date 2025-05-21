#map_fanatec_v0.1.py
import pygame
import time
import sys
import math # Import math for mapping if needed

# --- IMPORTANT: Replace these placeholders with your actual joystick and control indices! ---
# Use the output from the joystick_input_finder.py script to find these values.

STEER_JOYSTICK_INDEX = 1  # Example: Joystick index for the wheel
STEER_AXIS = 0            # Example: Axis index for steering rotation (usually -1.0 to 1.0)

THROTTLE_JOYSTICK_INDEX = 1 # Example: Joystick index for the pedals
THROTTLE_AXIS = 0         # Example: Axis index for the throttle pedal (check its range, e.g., -1.0 to 1.0 or 0.0 to 1.0)

BRAKE_JOYSTICK_INDEX = 1    # Example: Joystick index for the pedals
BRAKE_AXIS = 1            # Example: Axis index for the brake pedal (check its range)

# Example for a handbrake button (if you have one mapped)
# HANDBRAKE_JOYSTICK_INDEX = 0 # Example: Joystick index for the wheel or a separate handbrake
# HANDBRAKE_BUTTON = 8       # Example: Button index for the handbrake (0 for released, 1 for pressed)

# Example for gear shift buttons (if you use paddle shifters or a button box)
# GEAR_UP_JOYSTICK_INDEX = 0
# GEAR_UP_BUTTON = 5
# GEAR_DOWN_JOYSTICK_INDEX = 0
# GEAR_DOWN_BUTTON = 4

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

# Ensure the specified joysticks exist
if STEER_JOYSTICK_INDEX >= len(joysticks) or THROTTLE_JOYSTICK_INDEX >= len(joysticks) or BRAKE_JOYSTICK_INDEX >= len(joysticks):
     print("Error: Configured joystick index is out of range.")
     pygame.quit()
     sys.exit()

# Get references to the specific joysticks you need
steer_joystick = joysticks[STEER_JOYSTICK_INDEX]
throttle_joystick = joysticks[THROTTLE_JOYSTICK_INDEX]
brake_joystick = joysticks[BRAKE_JOYSTICK_INDEX]

# Optional: Get references for other joysticks if you mapped controls to them
# handbrake_joystick = joysticks[HANDBRAKE_JOYSTICK_INDEX] if 'HANDBRAKE_JOYSTICK_INDEX' in globals() else None
# gear_joystick = joysticks[GEAR_UP_JOYSTICK_INDEX] if 'GEAR_UP_JOYSTICK_INDEX' in globals() else None
# steer_joystick = joystick[STEER_JOYSTICK_INDEX]


print("\nReading controller inputs. Press Ctrl+C to exit.")

# --- Input Mapping Functions ---
# These functions take the raw joystick value and map it to CARLA's expected range
# You will need to adjust these based on your specific hardware's output range and feel.

def map_steering(raw_value):
    """Maps raw steering axis value (-1.0 to 1.0) to CARLA's steer range (-1.0 to 1.0)."""
    # Assuming raw_value is already -1.0 (left) to 1.0 (right)
    # Add a deadzone if needed
    deadzone = 0.05
    if abs(raw_value) < deadzone:
        return 0.0
    return raw_value # Simple direct mapping

def map_pedal(raw_value):
    """Maps raw pedal axis value to CARLA's throttle/brake range (0.0 to 1.0)."""
    # Assuming raw_value is -1.0 (released) to 1.0 (pressed) - common for Fanatec
    # We want 0.0 (released) to 1.0 (pressed)
    mapped_value = (raw_value + 1.0) / 2.0
    # Add a deadzone if needed (e.g., for the top of the pedal travel)
    deadzone = 0.02 # Example deadzone near released position
    if mapped_value < deadzone:
        return 0.0
    return mapped_value

# --- Data Structure to Store Current Control State ---
current_control_state = {
    'steer': 0.0,
    'throttle': 0.0,
    'brake': 0.0,
    'handbrake': 0, # 0 or 1 for button, or float for analog
    'reverse': 0,   # 0 or 1
    'manual_gear_shift': False, # True if manual shifting is active
    'gear': 1,      # Current gear (1 for Drive, 0 for Neutral/Reverse)
    # Add other controls as needed
}

# --- Real-time Input Reading and Storing Loop ---
try:
    while True:
        # Process Pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
            # Handle button presses/releases here to update control state
            if event.type == pygame.JOYBUTTONDOWN:
                 # Example: Toggle handbrake if button is pressed
                 # if 'HANDBRAKE_BUTTON' in globals() and event.joy == HANDBRAKE_JOYSTICK_INDEX and event.button == HANDBRAKE_BUTTON:
                 #     current_control_state['handbrake'] = 1 # Set to 1 while held, or toggle
                 pass # Add your button handling logic

            if event.type == pygame.JOYBUTTONUP:
                 # Example: Release handbrake
                 # if 'HANDBRAKE_BUTTON' in globals() and event.joy == HANDBRAKE_JOYSTICK_INDEX and event.button == HANDBRAKE_BUTTON:
                 #      current_control_state['handbrake'] = 0
                 pass # Add your button handling logic

            # Handle hat movements if you map anything to the D-pad
            # if event.type == pygame.JOYHATMOTION:
            #     if event.joy == HAT_JOYSTICK_INDEX and event.hat == HAT_INDEX:
            #          hat_direction = event.value # Tuple like (0, 1) for Up
            #          # Update control state based on hat direction (e.g., menu navigation)
            #          pass


        # Read and map axis values
        try:
            raw_steer = steer_joystick.get_axis(STEER_AXIS)
            current_control_state['steer'] = map_steering(raw_steer)

            raw_throttle = throttle_joystick.get_axis(THROTTLE_AXIS)
            current_control_state['throttle'] = map_pedal(raw_throttle) # Use map_pedal for throttle

            raw_brake = brake_joystick.get_axis(BRAKE_AXIS)
            current_control_state['brake'] = map_pedal(raw_brake)     # Use map_pedal for brake

            # Optional: Read other analog axes (e.g., clutch if you have one)
            # if 'CLUTCH_AXIS' in globals():
            #      raw_clutch = clutch_joystick.get_axis(CLUTCH_AXIS)
            #      current_control_state['clutch'] = map_pedal(raw_clutch) # Map clutch similarly

        except pygame.error as e:
             print(f"Error reading axis input: {e}")
             # Decide how to handle input errors - maybe set values to 0.0 or previous state

        # --- Now, current_control_state dictionary holds the latest mapped inputs ---
        # You would use these values to create and apply the carla.VehicleControl object.
        # Example (CARLA connection and vehicle object assumed to exist):
        # carla_control = carla.VehicleControl(
        #     throttle=float(current_control_state['throttle']),
        #     steer=float(current_control_state['steer']),
        #     brake=float(current_control_state['brake']),
        #     hand_brake=bool(current_control_state['handbrake']), # Convert 0/1 to bool
        #     reverse=bool(current_control_state['reverse']),
        #     manual_gear_shift=current_control_state['manual_gear_shift'],
        #     gear=current_control_state['gear']
        # )
        # vehicle.apply_control(carla_control)
        # world.tick() # If in synchronous mode

        # --- For demonstration, print the current state ---
        # You can comment this out in your final CARLA script
        print(f"Current Control State: Steer={current_control_state['steer']:.4f}, Throttle={current_control_state['throttle']:.4f}, Brake={current_control_state['brake']:.4f}", end='\r')


        # Small delay to control the loop speed (adjust to match desired simulation frequency)
        time.sleep(0.01) # Example: 100 updates per second

except KeyboardInterrupt:
    print("\nExiting script.")
except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")

finally:
    # --- Clean up ---
    pygame.joystick.quit()
    pygame.quit()
    print("Pygame quit.")

