<img src="./images/HBSS_logo.png" width="19.5%" style="float: left" >
<img src="./images/qryde_logo.png" width="40%" style="float: center">
<br style="clear: both;">
<hr>

# AI-Driven Behavioral Analysis in CARLA Simulation: Hardware-in-the-Loop with Fanatec Controllers and Nemotron Integration
<h2>
Project Description
</h2>
<font size=2>
[Briefly introduce the project's goal: developing a truck driving safety simulator using CARLA, Fanatec hardware, and an AI model for behavioral analysis.]
[Mention CARLA's suitability and validation as a platform.]

## Project Description:

This project focuses on developing an AI-enhanced system for the training and analysis of vehicle operator behavior within a dynamic simulated environment. Utilizing the CARLA driving simulator, a platform widely recognized and validated through numerous academic studies for its efficacy in safety assessment, we aim to provide a proof-of-concept for integrating advanced AI capabilities into driver evaluation.

The system incorporates real-world input from Fanatec steering and pedal hardware, creating a Hardware-in-the-Loop (HIL) simulation experience. Data streams generated from both the driver's physical inputs and the CARLA simulation's output (including vehicle kinematics, sensor data like semantic segmentation, collision events, and lane invasions) are processed by an AI model, specifically leveraging NVIDIA's Nemotron-Mini-4B-Instruct.

The AI model is designed to operate in two distinct modes to support comprehensive behavioral analysis:

1. Post-simulation Assessment: Analyzing the complete dataset logged during a driving session to provide in-depth insights into driver behavior patterns, risk assessment, and tendencies. This mode generates both structured numerical summaries (e.g., in tabular format) and detailed verbal feedback.

2. Live Integration: Processing real-time data streams from the HIL simulation and driver inputs via APIs. In this mode, the AI continuously evaluates safety metrics, identifies changes in driving patterns, and provides active warnings or feedback to the user during the simulation session, culminating in a summary upon completion.

Through this integration of realistic simulation, precise hardware input, and AI-driven analysis, the project seeks to demonstrate a powerful tool for enhancing driver training and safety evaluation. This project is also designed to permit further development and AI integration for robust analysis.


## AI Model Integration

[Explain the role of the AI model (Nemotron-Mini-Instruct) in processing data for driver behavior analysis, safety assessment, etc.]
[Clearly describe the two modes of operation:]
* **Post-simulation Assessment:** [Briefly explain what this mode does and the data it uses.]
* **Live Integration:** [Briefly explain what this mode does, the data streams it uses, and the type of feedback it provides.]

## Limitations

### Fanatec Simulation Kit

<p>
The Fanatec simulation kit (wheel + pedals) are not natively supported by CARLA and requires integration via additional python packages (pygame) and will require careful calibration. 
</p> 

### Versioning <br>
<p>
There are 2 concurrent versions of CARLA using 2 different physics engines being maintained by the CARLA developers. The most current is Unreal Engine 5 (UE5). Unreal Engine 5 represents a massive upgrade in realistic simulation, incorporating AI agents and more complimentary features. Based on current hardware configurations, we must run Unreal Engine 4 (UE4). It's unknown how long the developers will maintain the UE4 version. CARLA (UE4) runs on Python 3.9 which may be limiting when integrating some AI due to dependency issues.
</p>

### Hardware <br>
CARLA is a demanding program on the CPU and graphics card. The simulation kit adds to this. Lastly, incorporating an AI model - even a quantized "mini" 4B model - for inference & ML algorithms require a powerful card and stronger complementary components.
<p>

</p>
<font size=1>


| Component         | Current Setup                  | CARLA UE4 Minimum Requirements                     | Notes                                                                |
|-----------------|---------------------------|----------------------------------------------------|----------------------------------------------------------------------|
| **CPU**         | *Ryzen 5 5600G            | Quad-core Intel or AMD, 2.5 GHz or faster          |    |
| **RAM (Memory)** | *32GB Ripjaw V @ 2133 Mhz           | 16 GB RAM (32 GB recommended for building/large maps) | You meet the minimum RAM requirement. 32GB minimum is recommended for this project.     |
| **GPU (VRAM)**   | *8GB Nvidia Geforce RTX 3060 Ti\ 4GB Geforce RTX 1650 on pci | Dedicated GPU with at least 6 GB VRAM (8 GB recommended) | GPU meets minimum requirements but will overload running on multiple monitors or the 49" Samsung|
| **Storage**     | *1TB NVMe M.2 SSD + 256 SSD + 1TB HDD       | ~165 GB total (32 GB CARLA, ~133 GB UE4/deps)       | Ensure you have enough free space on your drives for the installation.|
| **Motherboard** | ASROCK B450m pro 4         | Not a standard requirement metric                   | Memory speed limitations (2133 mhz) impact CPU performance. Secondary PCI-E slots run PCI-E 3.0x1    |

<font size=2>
<b>Summary</b>: While the basic setup meets requirements, particularly the GPU, the involvement of an AI model, a single large monitor (or multiple monitors) will substantially increase the workload demand. The current secondary graphics card (RTX 1650) is limited by the PCI-E 3.0x1 bandwidth <i>and</i> the VRAM. 4GB is too small to handle an AI/ML model. 8GB in a secondary slot is not a possibility due to PCI-E speeds. Processor has too few cores and is too slow to handle highspeed AI/ML inference.
<br><br>

#### Recommendation:<br><font size=1>

| Component         | Current | 
|-----------------|---------------------------| 
|**CPU**         | Ryzen 9 7900X (12 core minimum)            | | **RAM (Memory)** | 32 GB DDR5-3600 (4800-6000 mhz even more ideal)
| **GPU (VRAM)**   | 24 GB Nvidia Geforce RTX 3090 or newer [3rd gen-328 tensor cores, 4th gen - 480 tensor cores, 5th gen 680 tensor cores]|
| **Storage**     | 2 TB Gen4 M.2 NVMe drive. Keep existing storage|
| **Motherboard** | ASUS or GIGABYTE X670-E with PCI-E 5.0 (for longevity) |

<font size=2>
The setup above will be suitable to run the Fanatec HIL kit + basic AI/ML operations + high resolution CARLA simulator (UE4) at low-middle settings with multiple monitors or 

## Workflow
### 1. Getting Data Output from CARLA via the Python API

Just as you use the CARLA Python API to send control commands to a vehicle (apply_control), you use the same API to retrieve information from the simulator.

Within your main simulation loop (the one where you're reading Pygame input and applying controls), you can access various data about the world and actors:

Vehicle State: You can get the current state of your controlled vehicle actor. Key information includes:

vehicle.get_transform(): Location and rotation in the world.
vehicle.get_velocity(): Linear velocity (speed and direction).
vehicle.get_angular_velocity(): Rotational velocity.
vehicle.get_acceleration(): Linear acceleration.
vehicle.get_control(): The control command currently being applied to the vehicle (useful for logging the actual control state, which might be slightly different from the command you sent if the simulator applies smoothing or limits).
vehicle.get_physics_control(): Detailed physics parameters (less likely needed for behavioral analysis, more for vehicle modeling).
Sensor Data: If you attach sensors to your vehicle (e.g., camera, LiDAR, collision detector, lane invasion detector), you can retrieve their data.

You would spawn sensor actors and attach them to your vehicle.
Each sensor has a listen() method that takes a callback function. This function is executed every time the sensor produces new data (e.g., every frame for a camera, or when a collision occurs for a collision sensor).
Inside the callback function, you receive the sensor data object (e.g., carla.Image, carla.LidarMeasurement, carla.CollisionEvent, carla.LaneInvasionEvent). This is where you would process or store the sensor-specific information.
World Information: You can get information about the simulation world itself:

world.get_snapshot(): A snapshot of the entire world state at a specific tick (useful in synchronous mode).
world.get_actors(): Get a list of all actors currently in the world.
world.get_map(): Access map information (road network, lane boundaries, etc.).
2. Relevant CARLA Output Data for Driving Behavior Analysis

For assessing driving behavior, the most relevant data from CARLA would typically include:

Vehicle Kinematics: Velocity, acceleration, angular velocity (to understand speed, acceleration/braking, turning rate).
Vehicle Location and Orientation: Position and rotation in the world (to track path, proximity to lane boundaries, position relative to other objects).
Collision Events (carla.CollisionEvent): Essential for detecting collisions, including information about the impulse and the other actor involved.
Lane Invasion Events (carla.LaneInvasionEvent): Reports when the vehicle crosses a lane marking, indicating potential lane deviations.
Obstacle Detection (from sensors like LiDAR or Camera + perception models): To identify proximity to other vehicles, pedestrians, or objects.
Traffic Light/Sign State: Information about traffic signals and signs the vehicle is encountering (can be inferred from location relative to actors or potentially via semantic segmentation data).
3. Combining Input and Output Data

Your main simulation loop will be the central point where you bring together the input and output data:

Input Data: Read from Pygame (joystick.get_axis, get_button, get_hat).
Output Data: Retrieve from CARLA (e.g., vehicle.get_velocity(), vehicle.get_transform(), and data received via sensor callbacks).
You need to ensure these data points are collected at roughly the same simulation timestamp (or tick in synchronous mode). In synchronous mode, calling world.tick() after applying controls and collecting data ensures everything is aligned for that specific simulation step.

4. Data Formatting for the AI Model

The format required by your Nemotron-Mini-Instruct model will depend on its specific API and how it's designed to receive input for analysis. However, you'll generally need to provide a structured representation of the driving state at each point in time.

Real-time Analysis (Warnings, Live Feedback):

You'll need to package the current state data in a format the AI model can process quickly.
This could be a dictionary or a list of key-value pairs containing the relevant parameters for the current simulation step: