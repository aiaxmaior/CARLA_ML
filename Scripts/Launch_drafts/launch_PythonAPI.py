import glob
import os
import sys

## Authors: Ankita Chandra, Arjun Joshi
## Date Started: 05/13/2025     
## Date Last Modified: 05/13/2025

"""
Purpose: 
This script spawns a vehicle in the Carla simulator and allows the user to control it using standard and custom
FANATEC simulation hardware.

FANATEC hardware data (steering wheel, pedals, etc.) is read using the `pygame` library and is transformed to fit
carla input formats.

(Current Status:
Testing launch, no pygame input yet.
)
"""

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla
import pygame
import math 
import time 
import random
import numpy as np


actor_list = []
# Start PythonAPI Server
try:
    client = carla.Client('localhost', 2000)
    client.set_timeout(2.0)
    world = client.get_world()
    blueprint_library = world.get_blueprint_library()
    map = world.get_map()
    spawn_points = map.get_spawn_points()

# Spawn Multiple Vehicles 
    number_of_vehicles = 10
    vehicle_blueprints = blueprint_library.filter('vehicle.*') 

    for i in range(number_of_vehicles):
        bp = random.choice(vehicle_blueprints)
        # Avoid spawning bikes and motorcycles for simplicity
        if bp.id.startswith('vehicle.motorcycle') or bp.id.startswith('vehicle.bicycle'):
            continue
        spawn_point = random.choice(spawn_points)
        
    try:
        new_vehicle = world.spawn_actor(bp, spawn_point)
        actor_list.append(new_vehicle)
        if i > 0:  # Make the first vehicle controllable (no autopilot for this simplified version)
            new_vehicle.set_autopilot(False)
        else:
            print(f"Controllable vehicle ID: {new_vehicle.id} ({new_vehicle.type_id}) spawned.")
    except RuntimeError:
        print(f"Warning: Could not spawn vehicle {bp.id}") # - {e}")
    time.sleep(5)  # Keep the vehicles spawned for 5 seconds
        
finally:
    print('destroying actors')
    for actor in actor_list:
        if actor.is_alive:
            actor.destroy()
    print('done.')