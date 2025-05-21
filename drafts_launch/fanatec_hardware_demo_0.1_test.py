import carla
import pygame
import time
import sys
import random # To choose a random spawn point
import cv2
import pandas as pd
import numpy as np
import math
import glob
import os
import matplotlib as plt

from carla import command

# Import your fanatec input module
import fanatec_input # Make sure fanatec_input.py is in the same directory

# Create functions
def get_basic_log_data(vehicle: carla.Vehicle) -> list:
    if vehicle is None or not isinstance(vehicle, carla.Vehicle):
        print("Error: Invalid vehicle object provided for logging.")
        return None
    try:
        
        location = vehicle.get_location()
        applied_control = vehicle.get_control()
        log_data = [
            applied_control.steer,
            applied_control.throttle,
            applied_control.brake,
            location.x,
            location.y,
            location.z]
        return log_data
    except Exception as e:
        print(f"Error retrieving basic log data: {e}")
        return None    
    
def spawn_pedestrian_in_front(world: carla.World, vehicle: carla.Vehicle, distance_in_front: float = 5.0):
    """
    Spawns a random pedestrian blueprint in front of a given vehicle actor.

    Args:
        world: The CARLA world object.
        vehicle: The CARLA vehicle actor object.
        distance_in_front: The distance in meters in front of the vehicle
                           to spawn the pedestrian.
    Returns:
        The spawned pedestrian actor object, or None if spawning fails.
    """
    if vehicle is None or not isinstance(vehicle, carla.Vehicle):
        print("Error: Invalid vehicle object provided.")
        return None

    try:
        # Get the blueprint library
        blueprint_library = world.get_blueprint_library()

        # Filter for pedestrian blueprints
        pedestrian_bps = blueprint_library.filter('walker.pedestrian.*')

        if not pedestrian_bps:
            print("Error: No pedestrian blueprints found.")
            return None

        # Choose a random pedestrian blueprint
        pedestrian_bp = random.choice(pedestrian_bps)

        # Ensure the blueprint is a walker
        if not pedestrian_bp.has_attribute('is_invincible'): # Check for a common walker attribute
             print(f"Warning: Selected blueprint {pedestrian_bp.id} is not a pedestrian. Skipping spawn.")
             return None

        # Get the vehicle's current transform (location and rotation)
        vehicle_transform = vehicle.get_transform()

        # Get the vehicle's forward vector
        forward_vector = vehicle_transform.get_forward_vector()

        # Calculate the spawn location in front of the vehicle
        # Add the forward vector scaled by the desired distance to the vehicle's location
        spawn_location = vehicle_transform.location + forward_vector * distance_in_front

        # Set the spawn location's Z coordinate to be slightly above the ground
        # This helps prevent the pedestrian from spawning inside the ground.
        # You might need to adjust this value (e.g., 0.5 or 1.0)
        spawn_location.z += 0.5

        # Create the spawn transform. Pedestrian should face the same direction as the car initially.
        spawn_transform = carla.Transform(spawn_location, vehicle_transform.rotation)

        # Spawn the pedestrian actor
        pedestrian_actor = world.try_spawn_actor(pedestrian_bp, spawn_transform)

        if pedestrian_actor:
            print(f"Spawned pedestrian: {pedestrian_actor.type_id} at {spawn_location}")
            # Optional: Make the pedestrian a controller and give it a simple task (e.g., walk forward)
            # walker_controller_bp = blueprint_library.find('controller.ai.walker')
            # world.spawn_actor(walker_controller_bp, carla.Transform(), attach_to=pedestrian_actor)
            # pedestrian_actor.start() # Start the walker AI controller
            # pedestrian_actor.go_to_location(carla.Location(x=spawn_location.x + forward_vector.x * 10, y=spawn_location.y + forward_vector.y * 10)) # Example: walk 10m forward

        else:
            print(f"Failed to spawn pedestrian at {spawn_location}. Is the location occupied?")

        return pedestrian_actor

    except Exception as e:
        print(f"An error occurred during pedestrian spawning: {e}")
        return None


"""
Retrieves basic log data (steer, throttle, brake, loc_x, loc_y, loc_z) for a vehicle.

Args:
    vehicle: The CARLA vehicle actor object.

Returns:
    A list containing [steer, throttle, brake, loc_x, loc_y, loc_z].
    Returns None if the vehicle object is invalid.
"""

# --- CARLA Connection and Setup ---
client = None
world = None
vehicle = None
original_settings = None
joysticks = [] # List to hold initialized pygame joysticks
log = pd.DataFrame(columns=['step','x','y','z','steer','throttle','brake']) 




try:
    # 1. Connect to the CARLA simulator
    client = carla.Client('localhost', 2000) # Adjust host and port if necessary
    client.set_timeout(120.0) # Set a timeout for connection

    # 2. Get the CARLA world object
    world = client.get_world()
    # 5. Find a suitable spawn point
    spawn_points = world.get_map().get_spawn_points()
    if not spawn_points:
        print("Error: No spawn points available in the map.")
        raise RuntimeError("No spawn points found")
        # Choose a random spawn point for the vehicle
    spawn_point = random.choice(spawn_points)
    print(f"Chosen spawn point: Location({spawn_point.location.x:.2f}, {spawn_point.location.y:.2f}, {spawn_point.location.z:.2f})")
    
    # 4. Set up Synchronous Mode (Recommended for control)
        
    # 6. Get a vehicle blueprint (e.g., a simple car)
    blueprint_library = world.get_blueprint_library()
    # You can choose a specific blueprint name here, or filter
    vehicle_bp = blueprint_library.find('vehicle.tesla.model3') # Example vehicle blueprint
    # vehicle_bp = random.choice(blueprint_library.filter('vehicle.*')) # Or a random vehicle
    vehicle_bp.set_attribute('role_name','hero')
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
    #carla.ShowDebugTelemetry(vehicle)==True
    #client.apply_batch([command.ShowDebugTelemetry(vehicle, True)])
    #command.show_debug_telemetry(vehicle, True)
    vehicle.show_debug_telemetry()
    print("Vehicle set to manual control.")

    # Optional: Set spectator view to follow the vehicle
    spectator = world.get_spectator()
    spectator_transform = carla.Transform(spawn_point.location + carla.Location(0.8,0,0.5))
    spectator.set_transform(spectator_transform)
    
    vehicle_transform = vehicle.get_transform()
    rotated_offset = vehicle_transform.transform_vector(driver_seat_offset_location)
    spectator_location = vehicle_transform.location+rotated_offset
    spectator_transform = carla.Transform(spectator_location, vehicle_transform.rotation)     
    spectator.set_transform(spectator_transform)
    # Optional: Set spectator view to follow the vehicle
    

# Define an offset for the driver's eye point relative to the vehicle's origin
# These values are approximate and might need tuning based on the specific vehicle model
# Positive X is forward, Positive Y is right, Positive Z is up
    driver_seat_offset_location = spectator.get_transform().location # Example offset

# Combine the vehicle's transform with the driver's seat offset
# This calculates the world location and rotation of the driver's viewpoint
    
    #Adjust the location and rotation of the spectator camera to be inside driver's seat
    
    driver_camera_location = vehicle.Location(x=0, y=0, z=1.8) # Adjust height to be at driver's eye level
    driver_camera_rotation = vehicle.Rotation(pitch=15.0, yaw=0.0, roll=0.0)
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
    
    axis_control_values = fanatec_input.get_fanatec_axis_input(joysticks)

    while True:
        # --- Process Pygame Events ---
        # This is important to keep the event queue from overflowing.
        # Handle button presses/releases and hat movements here if needed (e.g., gear shifts)
        # --- Set Spectator View --- #
        # Get the vehicle's current transform
        #vehicle_transform = vehicle.get_transform()

    # Define an offset for the driver's eye point relative to the vehicle's origin
    # These values are approximate and might need tuning based on the specific vehicle model
    # Positive X is forward, Positive Y is right, Positive Z is up
        driver_seat_offset_location = carla.Location(x=0.8, y=0.0, z=1.6) # Example offset

    # Combine the vehicle's transform with the driver's seat offset
    # This calculates the world location and rotation of the driver's viewpoint
        
# Set the spectator's transform to the calculated driver's viewpoint
        #spectator.set_transform(spectator_transform)


        world.tick()
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
            vehicle.throttle=0.1
            vehicle.steer=0
            vehicle.brake=0
            # --- Create and Apply CARLA VehicleControl ---
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
#        world.tick()

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

