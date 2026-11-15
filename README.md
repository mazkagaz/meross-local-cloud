# Meross HomeAssistant component (MRS100/local broker fork)

**THIS IS A WORK IN PROGRESS - DO NOT USE IT UNTILL I PUT OUT THIS MESSAGE**
**I ACTUALLY WORKED ON THE CODE BUT NOT THAT MUCH ON THE DOC, SO PLEASE WAIT**

## MRS100 / local-broker fork

This fork is distributed so it **WILL** be installed as a HACS **custom
repository** and used with the local Meross broker add-on
(`https://github.com/mazkagaz/meross-local-broker`, MRS100 fork). It keeps the existing Meross cloud
support, but when configured against the local broker it does not require the
Meross cloud for day-to-day device control.

- HACS -> Integrations -> three-dot menu -> Custom repositories
- URL: `https://github.com/mazkagaz/meross-cloud`
- Category: Integration
- Install, restart Home Assistant, then add the Meross Cloud integration and
  point it at the local broker API/MQTT endpoints.

The local broker add-on is installed separately through the Supervisor add-on
store; HACS cannot install add-ons.


A full-featured Homeassistant component to drive Meross devices. 
This component is based on the underlying MerossIot library available [here](https://github.com/albertogeniola/MerossIot).

This fork adds **roller-shutter open/close duration number entities** (`signalOpen`/`signalClose`) for MRS100-class covers. They pair with the local broker add-on, which persists and replays the timing across reconnects.

It also adds **start calibration** and **stop calibration** buttons using `Appliance.RollerShutter.Adjust`. Start sends `value=1` (the same command the Meross app uses); stop sends `value=0`. This covers the post-pairing calibration step without the Meross app. The command path sends the raw namespace string because `meross_iot` 0.4.9.2 does not define a `ROLLER_SHUTTER_ADJUST` enum member.

A **Calibration status** diagnostic sensor reports the result: `success`, `timeout`, `motor_blocked`, `failed_3`..`failed_6`, plus `in_progress` locally after a start. It polls `GET Appliance.RollerShutter.Adjust` every 5 minutes, and after a start every 15 seconds for two minutes following a 90 s delay (the official app waits 90 s before its first status poll). `meross_iot` 0.4.9.2 drops incoming Adjust pushes, so push-based status is not available without a library change.

## Installation & configuration
You **WILL BE ABLE TO** install this component in two ways: via HACS (**IN THE FUTURE**) or manually.

### Option A: Installing via HACS
Not yet

### Option B: Classic installation (custom_component)
1. Download the latest zip release archive from [here](https://github.com/mazkagaz/meross-cloud/releases/latest)
1. Unzip/copy the meross_cloud directory within the `custom_components` directory of your homeassistant installation.
The `custom_components` directory resides within your homeassistant configuration directory.
Usually, the configuration directory is within your home (`~/.homeassistant/`).
In other words, the configuration directory of homeassistant is where the config.yaml file is located.
After a correct installation, your configuration directory should look like the following.
    ```
    └── ...
    └── configuration.yaml
    └── secrects.yaml
    └── custom_components
        └── meross_cloud
            └── __init__.py
            └── common.py
            └── cover.py
            └── ...
    ```

    **Note**: if the custom_components directory does not exist, you need to create it.

After copy-pasting the meross_cloud directory into the custom_components folder, you need to restart HomeAssistant.
As soon as HomeAssistant is restarted, you can proceed with __component setup__.

### Component setup    
Once the component has been installed, you need to configure it in order to make it work.
To do so, navigate to "Configuration -> Integrations -> Add Integration" and look for "Meross Cloud IoT".
As soon as you add it, you'll be asked to configure it. 
The following table summarizes the fields that the wizard will require you to fill in:

**TODO: UPDATE THE TABLE**

|  Field Name                      | Example Value           | Description                                             | 
|----------------------------------|-------------------------|---------------------------------------------------------|
| HTTP Api Endpoint                | One of the following: <br/> - https://iotx-ap.meross.com (for Asia/Pacific regions) <br/> - https://iotx-eu.meross.com (for Europe) <br/> - https://iotx-us.meross.com (for United States) | Is the HTTP(s) API endpoint used by the Meross Manager. This might vary in accordance with your country | 
| Email Address                    | johndoe@gmail.com       | Your Meross account username/email. If connecting to the official Meross cloud, use the same from the Meross App |
| Password                         | R4nd0mS3cret            | Your Meross account password. If connecting to the official Meross cloud, use the same from the Meross App |
| Skip MQTT certificate validation | True (Checked)          | Configures MQTT certificate validation. When unchecked it requires a valid certificate to be exposed from the Meross Server. If checked, it skips the MQTT certificate validation. If connecting to the official Meross cloud, you can uncheck this. When connecting to local-lan or custom MQTT brokers, you might want to check this. |


## Features
### Support
This library supports all the Meross devices currently exposed by the Albertogeniola Meross IoT library.
In particular Bulbs, Switches, Garage Door Openers and Smart Valves/Thermostat are fully supported and perfectly integrated with HomeAssistant.


## A fork version of the Albertogeniola Local-Only Addon is [here](https://github.com/mazkagaz/meross-local-broker)
It is an **unstable** version of the Local Meross Addon. I am working on integrationg MRS100.
Please note that the usage of the Local Addon is only advised for all the advanced users who are experiencing problems with Meross security
team, complaining about high rate API calls to their systems. If you plan to use such devices off-grid, the Local Addon is what you are
looking for. Again, be avised: it's still a work in progress of a fork of a work in progress... :-D ... and your devices might not work as expected (for now).

You can find installation instructions for the Local Addon directly [here](https://github.com/mazkagaz/meross-local-broker).

### What is the local-addon?
Meross Plugin has gained great success and popularity among the HomeAssistant users. However, the Meross engineers are imposing
new limits on their MQTT broker system, which cause problems to the HA users who want to implement aggressive polling or have
more than 10 devices connected to HA. For this reason, Albertogeniola is working on a new HomeAssistant addon, namely "Meross Local Addon", 
which aims at re-implementing the Meross MQTT Broker and HTTP API layer locally to the addon. This would basically allow users
to rely only on LAN-local connection, using HomeAssistant as command center. And as i am not a patient person, i forked it. 

### How to use this Meross Component with the Local Addon?
In order to take advantage of the Local Meross Addon, you need to follow the instructions below:
1. Install or update the version of the Meross Custom Component at least to version 1.2.5rc1, 
which is the first one supporting the Meross Local Addon.
2. Add the Meross Local Addon repository to your HomeAssistant installation. You can do that following the [instructions here]([url](https://github.com/mazkagaz/meross-local-broker)) or simply press the following button

    [![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmazkagaz%2Fmeross-local-broker)
3. Make sure the "Meross Local Addon for Homeassistant" appears in the section of "community addons" and, if so, install it.

### How to switch from a cloud based integration to a local integration
_Credits to @olivermaor_

When switching from a cloud based to a local integration, it is important that the correct sequence of steps is followed:
1. Install the "Meross Local Addon", as described above, but do not start it yet.
2. In the Settings - Integration panel, open the existing Meross IoT integration and copy or print the friendly names of the devices used.
3. Go back to the Settings - Integration panel and delete the Meross IoT integration.
4. Reboot Home Assistant.
5. After the reboot has finished, access the file /config/.storage/core.entity_registry, and copy that file into the same directory as a backup (use a name like core.entity_registry_backup)
6. After having backed up that file, open it (not the backup) with an editor, and find obsolete entries of entities which derive from the Meross IoT integration. Each entity is enclosed in a set of brackets (*{* *}*). Delete these entries, and only these entries, this including the respective brackets. Be careful: The entities are separated by commas, but after the last entry in the entire list, a comma may not be set.
7. Save the amended file, and reboot Home Assistant. If you made mistakes editing the core.entity_registry file, you can still revert to the backup.
8. Now start the "Meross Local Addon" and pair the Meross devices **one by one**, using the pairing app. After each device had been successsfully paired, rename it **in the addon**, using **exactly** the friendly name which the device had before, when you used the cloud integration. Wait until it shows "online", eventually refreshing the browser page. Only after having done that, pair the next device.
9. Be sure you have paired all devices, and changed their "friendly names". Only then add the Meross IoT integration, and select the local broker, as described above. Your devices will be re-discovered with the correct friendly names, and can be integrated into HA.
10. If you have followed these steps, all devices should again work with all scenes and automations as before.

## Supporting his work
This is a fork of Albertogeniola work.
[![Buy him a coffe!](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/albertogeniola)

I may add my coffe box later when this will work as I would like it to work.

## License and attribution

This is an **unofficial fork** of
[albertogeniola/meross-homeassistant](https://github.com/albertogeniola/meross-homeassistant).
Upstream code is Copyright (c) 2023 Alberto Geniola under the **MIT License**.
The original copyright and permission notice are preserved in `LICENSE`, with
an added line for the fork modifications (Copyright (c) 2026 the MRS100 fork
contributors, MIT). See `NOTICE`, `MODIFICATIONS.md` and `LEGAL.md`.

Meross is a trademark of its respective owner. This fork is not affiliated
with, endorsed by, or sponsored by Meross or the upstream author. No Meross
firmware, APK or account secret is distributed here.
