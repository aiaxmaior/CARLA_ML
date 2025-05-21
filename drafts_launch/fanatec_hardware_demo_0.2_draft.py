import carla
import pygame
import time
import sys
import random # To choose a random spawn point
import cv2
from carla import command

# Import your fanatec input module
import fanatec_input # Make sure fanatec_input.py is in the same directory

###########
"""
# --- Pygame Setup ---
pygame.init()
display_width = 800
display_height = 600
display = pygame.display.set_mode((display_width, display_height))
pygame.display.set_caption("CARLA Manual Control with Telemetry")
white = (255, 255, 255)
black = (0, 0, 0)
font = pygame.font.Font(None, 30)
############
"""
# --- CARLA Connection and Setup ---
client = None
world = None
vehicle = None
original_settings = None
joysticks = [] # List to hold initialized pygame joysticks



try:
    # 1. Connect to the CARLA simulator
    client = carla.Client('localhost', 2000) # Adjust host and port if necessary
    client.set_timeout(120.0) # Set a timeout for connection

    # 2. Get the CARLA world object
    world = client.get_world()

    # 3. Load the specified map
    # Check if the current map is already the desired map
    if world.get_map().name != "Town10HD_Opt":
        print("Loading map: Town10HD_Opt")
        world = client.load_world("Town10HD_Opt")
        # Give the server some time to load the world
        time.sleep(5.0) # Adjust sleep time based on your system speed

    print("Map loaded.")

    # 5. Find a suitable spawn point
    spawn_points = world.get_map().get_spawn_points()
    if not spawn_points:
        print("Error: No spawn points available in the map.")
        raise RuntimeError("No spawn points found")
        # Choose a random spawn point for the vehicle
    spawn_point = random.choice(spawn_points)
    print(f"Chosen spawn point: Location({spawn_point.location.x:.2f}, {spawn_point.location.y:.2f}, {spawn_point.location.z:.2f})")
    
    # 4. Set up Synchronous Mode (Recommended for control)
    """
    original_settings = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True # Enables synchronous mode
    settings.fixed_delta_seconds = 0.05 # Set a fixed time step (e.g., 20 FPS)
    world.apply_settings(settings)
    print("Synchronous mode enabled.")
"""
        
    # 6. Get a vehicle blueprint (e.g., a simple car)
    blueprint_library = world.get_blueprint_library()
    # You can choose a specific blueprint name here, or filter
    vehicle_bp = blueprint_library.filter('vehicle.tesla.model3')[0] # Example vehicle blueprint
    # vehicle_bp = random.choice(blueprint_library.filter('vehicle.*')) # Or a random vehicle

    # 7. Spawn the vehicle
    print("Spawning vehicle...")
    vehicle = world.spawn_actor(vehicle_bp, spawn_point)
    print(f"Spawned vehicle: {vehicle.type_id} at {spawn_point.location}")

    # 8. Set the vehicle to manual control (disable autopilot if it was on)
    # The code snippet `vehicle.set_autopilot(False)` followed by `print("Vehicle set to manual
    # control.")` is setting the vehicle to manual control mode in the CARLA simulator. By calling
    # `vehicle.set_autopilot(False)`, you are disabling the autopilot feature for the vehicle, which
    # means the vehicle will no longer be controlled by any autonomous driving algorithms within the
    # simulator. Instead, it will be controlled manually based on the input provided through the
    # Fanatec hardware or any other input mechanism you have set up in the script. The subsequent
    # print statement is just a confirmation message indicating that the vehicle has been successfully
    # switched to manual control mode.
    vehicle.set_autopilot(False)
     # --- Enable Debug Telemetry for the Vehicle ---
    client.apply_batch([command.ShowDebugTelemetry(vehicle, True)])
    print("Debug telemetry enabled for the vehicle.")
    print("Vehicle set to manual control.")

    """ # Optional: Set spectator view to follow the vehicle
    spectator = world.get_spectator()
    spectator_transform = carla.Transform(spawn_point.location + carla.Location(z=50), carla.Rotation(pitch=-90))
    spectator.set_transform(spectator_transform)
    """


    # Optional: Set spectator view to follow the vehicle
    spectator = world.get_spectator()
    vehicle_transform = vehicle.get_transform()
    
    #Adjust the location and rotation of the spectator camera to be inside driver's seat
    driver_camera_location = carla.Location(x=0, y=0, z=1.8) # Adjust height to be at driver's eye level
    driver_camera_rotation = carla.Rotation(pitch=15.0, yaw=0.0, roll=0.0)
    spectator_transform = carla.Transform(spawn_point.location + carla.Location(z=50), carla.Rotation(pitch=-90))
    
    # --- Pygame Setup (Initialize and find joysticks) ---
    pygame.init()
    pygame.joystick.init()

    joystick_count = pygame.joystick.get_count()
    if joystick_count == 0:
        print("Error: No joysticks found. Connect your Fanatec wheel kit.")
        # Continue without joystick control, or exit
        # pygame.quit()
        # sys.exit()
        joysticks = [] # Ensure joysticks list is empty if none found
    else:
        print(f"Found {joystick_count} joystick(s) via Pygame.")
        for i in range(joystick_count):
            try:
                joystick = pygame.joystick.Joystick(i)
                joystick.init()
                joysticks.append(joystick)
                print(f"  Initialized Joystick {i}: {joystick.get_name()}")
            except pygame.error as e:
                print(f"  Error initializing joystick {i}: {e}")

        if not joysticks:
            print("Error: No joysticks could be successfully initialized.")
            # Decide how to handle this - exit or run without control
            # pygame.quit()
            # sys.exit()


    # --- Main Simulation Loop ---
    print("\nStarting simulation loop. Control the vehicle with your Fanatec hardware.")
    print("Press Ctrl+C in the terminal to exit.")

    while True:
        # --- Process Pygame Events ---
        # This is important to keep the event queue from overflowing.
        # Handle button presses/releases and hat movements here if needed (e.g., gear shifts)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
            # Add specific event handling logic here based on event.type, event.joy, event.button/hat, event.value
            # Example: Check for a button press to toggle handbrake
            # if event.type == pygame.JOYBUTTONDOWN:
            #      if event.joy == fanatec_input.HANDBRAKE_JOYSTICK_ID and event.button == fanatec_input.HANDBRAKE_BUTTON:
            #           current_handbrake_state = not current_handbrake_state # Toggle state


        # --- Get Fanatec Control Input ---
        # Call the function from your fanatec_input script
        # Pass the list of initialized joysticks
        # This function reads the CURRENT state of axes
        if joysticks: # Only attempt to get input if joysticks were found and initialized
            axis_control_values = fanatec_input.get_fanatec_axis_input(joysticks)

            # --- Combine Axis and Button/Hat States ---
            # If you handle buttons/hats in the event loop and store their states
            # in variables in your main script, combine them here with axis_control_values
            # For this basic demo, we'll just use axis values directly for control
            current_control_state = {
                'steer': axis_control_values.get('steer', 0.0), # Use .get with default to be safe
                'throttle': axis_control_values.get('throttle', 0.0),
                'brake': axis_control_values.get('brake', 0.1),
                'handbrake': False, # Default or get state from event handling
                'reverse': False,   # Default or get state from event handling
                'manual_gear_shift': False, # Default or get state from event handling
                'gear': 1           # Default or get state from event handling
            }


            # --- Create and Apply CARLA VehicleControl ---
            carla_control = carla.VehicleControl(
                throttle=float(current_control_state['throttle']),
                steer=float(current_control_state['steer']),
                brake=float(current_control_state['brake']),
                hand_brake=bool(current_control_state['handbrake']),
                reverse=bool(current_control_state['reverse']),
                manual_gear_shift=bool(current_control_state['manual_gear_shift']),
                gear=int(current_control_state['gear'])
            )

            # Apply the control to the vehicle actor
            vehicle.apply_control(carla_control)

        else:
            # If no joysticks found, apply neutral control or autopilot
            neutral_control = carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0) # Apply brake if no input
            vehicle.apply_control(neutral_control)
            # Or set autopilot: vehicle.set_autopilot(True) # Requires traffic manager


        # --- Tick the CARLA World (in synchronous mode) ---
        # This advances the simulation by one step
        world.tick()

        # Optional: Update spectator view to follow the vehicle
        spectator_transform = vehicle.get_transform()
        spectator.set_transform(carla.Transform(spectator_transform.location + carla.Location(z=50), carla.Rotation(pitch=-90)))


except KeyboardInterrupt:
    print("\nExiting simulation.")
except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")

finally:
    # --- Clean up ---
    print("Cleaning up...")
    if vehicle is not None and vehicle.is_alive:
        print("Destroying vehicle...")
        vehicle.destroy()
        vehicle = None
    if world is not None and original_settings is not None:
        print("Restoring original CARLA settings...")
        world.apply_settings(original_settings) # Restore async mode etc.
    if pygame.joystick.get_init(): # Check if joystick module was initialized
        pygame.joystick.quit()
        print("Pygame joystick quit.")
    if pygame.get_init(): # Check if pygame was initialized
        pygame.quit()
        print("Pygame quit.")
    print("Script finished.")

