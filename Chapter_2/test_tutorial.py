#!/usr/bin/env python

# Copyright (c) 2019 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB).
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

import glob
import os
import sys

from queue import Queue
from queue import Empty

import random
import time


try:
    import numpy as np
except ImportError:
    raise RuntimeError(
        'cannot import numpy, make sure numpy package is installed')

# ==============================================================================
# -- Find CARLA module ---------------------------------------------------------
# ==============================================================================
try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass


# ==============================================================================
# -- Add PythonAPI for release mode --------------------------------------------
# ==============================================================================
try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + '/carla')
except IndexError:
    pass

import carla
from carla import ColorConverter as cc

from agents.navigation.behavior_agent import BehaviorAgent  # pylint: disable=import-error
from agents.navigation.basic_agent import BasicAgent  # pylint: disable=import-error



def sensor_callback(sensor_data, sensor_queue, sensor_name):
    if 'lidar' in sensor_name:
        sensor_data.save_to_disk('_out/%06d.png' % sensor_data.frame)
    if 'camera' in sensor_name:
        sensor_data.save_to_disk('_out/%06d.png' % sensor_data.frame)
    sensor_queue.put((sensor_data.frame, sensor_name))


def main():
    
    actor_list = []
    picked_spawn_points_list = []
    
    # In this tutorial script, we are going to add a vehicle to the simulation
    # and let it drive in autopilot. We will also create a camera attached to
    # that vehicle, and save all the images generated by the camera to disk.
    
    try:
        # First of all, we need to create the client that will send the requests
        # to the simulator. Here we'll assume the simulator is accepting
        # requests in the localhost at port 2000.
        client = carla.Client('localhost', 2000)
        client.set_timeout(10.0)
        
        # Once we have a client we can retrieve the world that is currently
        # running.
        world = client.get_world()
    
        # set sync mode
        settings = world.get_settings()
        settings.synchronous_mode = True
        # 20fps
        settings.fixed_delta_seconds = 0.05
        world.apply_settings(settings)

        
        # Set the weather
        weather = carla.WeatherParameters(cloudiness=10.0,
                                          precipitation=0.0,
                                          sun_altitude_angle=70.0,
                                          fog_density=0.0)
        world.set_weather(weather)
        
        
        # Traffic manager and its sync mode
        tm = client.get_trafficmanager(8000)
        tm.set_synchronous_mode(True) 
        
        # The world contains the list blueprints that we can use for adding new
        # actors into the simulation.
        blueprint_library = world.get_blueprint_library()

        # Now let's filter all the blueprints of type 'vehicle' and choose one
        # at random.
        vehicle1_bp = random.choice(blueprint_library.filter('vehicle'))

        # A blueprint contains the list of attributes that define a vehicle's
        # instance, we can read them and modify some of them. For instance,
        # let's randomize its color.
        if vehicle1_bp.has_attribute('color'):
            vehicle1_bp.set_attribute('color', '255,255,255')
            
        # get avaliable spawn points 
        spawn_points = world.get_map().get_spawn_points()
        random.shuffle(spawn_points)

        # Now we need to give an initial transform to the vehicle. We choose a
        # random transform from the list of recommended spawn points of the map.
                
        vehicle1_spawn_point = spawn_points[-1]
        vehicle1 = world.spawn_actor(vehicle1_bp, vehicle1_spawn_point)
        picked_spawn_points_list.append(vehicle1_spawn_point)

        # So let's tell the world to spawn the vehicle.

        # It is important to note that the actors we create won't be destroyed
        # unless we call their "destroy" function. If we fail to call "destroy"
        # they will stay in the simulation even after we quit the Python script.
        # For that reason, we are storing all the actors we create so we can
        # destroy them afterwards.
        actor_list.append(vehicle1)
        print('created %s' % vehicle1.type_id)

        # Let's put the vehicle to drive around.
        vehicle1.set_autopilot(True,8000)
        
        # Add another 10 random vehicles and store all the 10 vehicles in link list vehicle and
        # destroy them afterwards.
        NUMBER_OF_VEHICLES = 10

        vehicle_bps = world.get_blueprint_library().filter('vehicle.*.*')

        vehicle_bps = [x for x in vehicle_bps if int(x.get_attribute('number_of_wheels')) == 4]

        vehicle_list = []

        for i in range(NUMBER_OF_VEHICLES):
            point = spawn_points[i]
            vehicle_bp = np.random.choice(vehicle_bps)
            try:
                vehicle = world.spawn_actor(vehicle_bp, point)
                picked_spawn_points_list.append(point)
                vehicle_list.append(vehicle)
                vehicle.set_autopilot(True,8000)
                print('created %s' % vehicle.type_id)
                
            except:
                print('failed')
                pass
            
            
        # set several of the cars as dangerous car with traffic manager
        
        # set the difference the vehicle's intended speed and its current speed limit
        tm.global_percentage_speed_difference(30.0)

        tm_port = tm.get_port()
        for v in vehicle_list:
            v.set_autopilot(True, tm_port)
            
            # tell the vehicle to ignore traffic lights in 5% of cases
            tm.ignore_lights_percentage(v,5)
            
            # tell the vehicle to keep a safe distance of 2 meters from the vehicle in front
            tm.distance_to_leading_vehicle(v,2)
            
            #tell the vehicle that the target speed is 20% overspeed
            tm.vehicle_percentage_speed_difference(v,-20)

        
        # create sensor queue
        sensor_queue = Queue(maxsize=10)

        # Let's add now a camera attached to the vehicle. Note that the
        # transform we give here is now relative to the vehicle.
        camera_bp = blueprint_library.find('sensor.camera.rgb')
        camera_transform = carla.Transform(carla.Location(x=-5, z=2))
        camera = world.spawn_actor(camera_bp, camera_transform, attach_to=vehicle1)
        actor_list.append(camera)
        print('created %s' % camera.type_id)
        
        # set the callback function
        # register the function that will be called each time the sensor
        # receives an image. In this example we are saving the image to disk
        camera.listen(lambda image: sensor_callback(image, sensor_queue, "camera"))
        
        
        # we need to tick the world once to let the client update the spawn position
        world.tick()
        
        # create the behavior agent
        agent = BehaviorAgent(vehicle1, behavior='normal')

        # set the destination spot
        spawn_points = world.get_map().get_spawn_points()
        random.shuffle(spawn_points)

        # to avoid the destination and start position same
        if spawn_points[0].location != agent._vehicle.get_location():
            destination = spawn_points[0]
        else:
            destination = spawn_points[1]
        
        print('moved vehicle from %s' % agent._vehicle.get_location())
        print('moved vehicle to %s' % destination.location)

        # generate the route
        agent.set_destination( destination.location)

        
        while True:
            agent._update_information()
        
            world.tick()
            data = sensor_queue.get(block=True)
            
            if len(agent._local_planner._waypoints_queue)<1:
                print('======== Success, Arrivied at Target Point!')
                break
                
            # set the sectator to follow the ego vehicle (top view)
            spectator = world.get_spectator()
            transform = vehicle1.get_transform()
            spectator.set_transform(carla.Transform(transform.location + carla.Location(z=40),
                                                    carla.Rotation(pitch=-90)))
            actor_list.append(spectator)

            speed_limit = vehicle1.get_speed_limit()
            agent.get_local_planner().set_speed(speed_limit)
            
            control = agent.run_step(debug=True)
            vehicle1.apply_control(control)


    finally:
        
        settings = world.get_settings()
        settings.synchronous_mode = False
        settings.fixed_delta_seconds = None
        world.apply_settings(settings)

        print('destroying actors')
        client.apply_batch([carla.command.DestroyActor(x) for x in actor_list])
        client.apply_batch([carla.command.DestroyActor(x) for x in vehicle_list])
        print('done.')

if __name__ == '__main__':

    main()
    