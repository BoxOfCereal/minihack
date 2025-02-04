#!/usr/bin/env python
#
# Copyright (c) Facebook, Inc. and its affiliates.
import argparse
import ast
import contextlib
import random
import os
import termios
import time
import timeit
import tty

import gym

import nle  # noqa: F401
import minihack  # noqa: F401
from nle import nethack
import tempfile
import shutil
import glob
import json
import os
import numpy as np
from PIL import Image


_ACTIONS = tuple(
    [nethack.MiscAction.MORE]
    + list(nethack.CompassDirection)
    + list(nethack.CompassDirectionLonger)
)


@contextlib.contextmanager
def dummy_context():
    yield None


@contextlib.contextmanager
def no_echo():
    tt = termios.tcgetattr(0)
    try:
        tty.setraw(0)
        yield
    finally:
        termios.tcsetattr(0, termios.TCSAFLUSH, tt)


def get_action(env, action_mode, is_raw_env):
    if action_mode == "random":
        if not is_raw_env:
            action = env.action_space.sample()
        else:
            action = random.choice(_ACTIONS)
    elif action_mode == "human":
        while True:
            with no_echo():
                ch = ord(os.read(0, 1))
            if ch == nethack.C("c"):
                print("Received exit code {}. Aborting.".format(ch))
                return None
            try:
                if is_raw_env:
                    action = ch
                else:
                    action = env.actions.index(ch)
                break
            except ValueError:
                print(
                    (
                        "Selected action '%s' is not in action list. "
                        "Please try again."
                    )
                    % chr(ch)
                )
                continue
    return action


def play(
    env,
    mode,
    ngames,
    max_steps,
    seeds,
    savedir,
    no_render,
    render_mode,
    debug,
    save_gif,
    gif_path,
    gif_duration,
    dump_observations,
    instruction
):
    env_name = env
    is_raw_env = env_name == "raw"

    if is_raw_env:
        if savedir is not None:
            os.makedirs(savedir, exist_ok=True)
            ttyrec = os.path.join(savedir, "nle.ttyrec.bz2")
        else:
            ttyrec = "/dev/null"
        env = nethack.Nethack(ttyrec=ttyrec)
    else:
        env_kwargs = dict(
            savedir=savedir,
            max_episode_steps=max_steps,
        )
        if save_gif:
            env_kwargs["observation_keys"] = ("pixel_crop",)
            try:
                import PIL.Image
            except ModuleNotFoundError:
                raise ModuleNotFoundError(
                    "To safe GIF files of trajectories, please install Pillow:"
                    " pip install Pillow"
                )
            
        if dump_observations:
            if "observation_keys" not in env_kwargs:
                env_kwargs["observation_keys"] = ()  # Create empty observation keys if not present

            observation_keys_to_add = tuple(dump_observations)
            env_kwargs["observation_keys"] += tuple(observation_keys_to_add)

        # print(env_kwargs["observation_keys"])
        # print(env_kwargs)


        env = gym.make(
            env_name,
            **env_kwargs,
        )
        if seeds is not None:
            env.seed(seeds)
        if not no_render:
            print("Available actions:", env.actions)

    obs = env.reset()

    steps = 0
    episodes = 0
    reward = 0.0
    action = None

    mean_sps = 0
    mean_reward = 0.0

    total_start_time = timeit.default_timer()
    start_time = total_start_time

    if save_gif:
        # Create a tmp directory for individual screenshots
        tmpdir = tempfile.mkdtemp()

    turn = 0
    while True:
        if not no_render:
            if not is_raw_env:
                print("Previous reward:", reward)
                if action is not None:
                    print("Previous action: %s" % repr(env.actions[action]))
                env.render(render_mode)
            else:
                print("Previous action:", action)
                _, chars, _, _, blstats, message, *_ = obs
                msg = bytes(message)
                print(msg[: msg.index(b"\0")])
                for line in chars:
                    print(line.tobytes().decode("utf-8"))
                print(blstats)
        
        if dump_observations:
            print(f"Selected observations to dump",dump_observations)

            jsonl_file_path = os.path.join(savedir, 'data.jsonl')
            print(jsonl_file_path)

            # Create the directory if it doesn't exist
            if not os.path.exists(savedir):
                os.makedirs(savedir)

            # Iterate over observations + process
            with open(jsonl_file_path, 'a') as jsonl_file:
                # Create JSON entry with all observations from obs dictionary
                json_entry = {'env_name': env_name,'instruction':instruction,'t': turn,'goal':'','action':action}
                wanted_keys = dump_observations
                observations = dict((k, obs[k]) for k in wanted_keys if k in obs)

                string_observations = ["chars", "chars_crop", "tty_chars", "tty_chars_crop", "message",
                       "screen_descriptions", "screen_descriptions_crop", "inv_letters",
                       "inv_oclasses", "inv_strs"]

                # Save image for 'pixel' and 'pixel_crop' keys
                observations = {
                    key: (Image.fromarray(value).save(os.path.join(savedir, (key + f"_path{turn}.jpg"))) or key + f"_path{turn}.jpg")
                    if key in ['pixel', 'pixel_crop'] else value
                    for key, value in observations.items()
                }

                # Decode values for specified keys
                observations = {
                    key: [item.tobytes().decode("utf-8").replace("\u0000", "").strip() for item in value]
                    if key in string_observations else value
                    for key, value in observations.items()
                }

                # Convert 2D array to a single string with new lines for specified keys
                observations = {
                    key: "\n".join("".join(row) for row in value)
                    if key in ['chars', 'chars_crop', 'tty_chars', 'tty_chars_crop'] else value
                    for key, value in observations.items()
                }

                # Convert ndarray values to lists
                observations = {
                    key: value.tolist() if isinstance(value, np.ndarray) else value
                    for key, value in observations.items()
                }

                # Remove empty string elements from 'inv_strs' list if present
                observations['inv_strs'] = [item for item in observations.get('inv_strs', []) if item != '']

                # Concatenate 'message' elements into a single string and remove extra whitespace
                observations['message'] = ''.join([s if s != '' else ' ' for s in observations['message']]).strip()   

                # Add all observations
                json_entry.update(observations) 
               
                # Write JSON entry to the JSONL file
                jsonl_file.write(json.dumps(json_entry) + '\n')

                # Increment the turn
                turn += 1

            print("JSON objects and images saved successfully.")
                
        if save_gif:
            obs_image = PIL.Image.fromarray(obs["pixel_crop"])
            obs_image.save(os.path.join(tmpdir, f"e_{episodes}_s_{steps}.png"))

        action = get_action(env, mode, is_raw_env)
        if action is None:
            break

        if is_raw_env:
            obs, done = env.step(action)
        else:
            obs, reward, done, info = env.step(action)
        steps += 1

        if is_raw_env:
            done = done or steps >= max_steps  # NLE does this by default.
        else:
            mean_reward += (reward - mean_reward) / steps

        if not done:
            continue

        time_delta = timeit.default_timer() - start_time

        if not is_raw_env:
            print("Final reward:", reward)
            print("End status:", info["end_status"].name)
            print("Mean reward:", mean_reward)

        sps = steps / time_delta
        print("Episode: %i. Steps: %i. SPS: %f" % (episodes, steps, sps))

        episodes += 1
        mean_sps += (sps - mean_sps) / episodes

        start_time = timeit.default_timer()

        steps = 0
        mean_reward = 0.0

        if episodes == ngames:
            break
        env.reset()

    if save_gif:
        # Make the GIF and delete the temporary directory
        png_files = glob.glob(os.path.join(tmpdir, "e_*_s_*.png"))
        png_files.sort(key=os.path.getmtime)

        img, *imgs = [PIL.Image.open(f) for f in png_files]
        img.save(
            fp=gif_path,
            format="GIF",
            append_images=imgs,
            save_all=True,
            duration=gif_duration,
            loop=0,
        )
        shutil.rmtree(tmpdir)

        print("Saving replay GIF at {}".format(os.path.abspath(gif_path)))
    env.close()
    print(
        "Finished after %i episodes and %f seconds. Mean sps: %f"
        % (episodes, timeit.default_timer() - total_start_time, mean_sps)
    )


def main():
    parser = argparse.ArgumentParser(description="Play tool.")
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enables debug mode, which will drop stack into "
        "an ipdb shell if an exception is raised.",
    )
    parser.add_argument(
        "-m",
        "--mode",
        type=str,
        default="human",
        choices=["human", "random"],
        help="Control mode. Defaults to 'human'.",
    )
    parser.add_argument(
        "-e",
        "--env",
        type=str,
        default="MiniHack-Room-Random-5x5-v0",
        help="Gym environment spec. Defaults to 'MiniHack-Room-Random-5x5-v0'.",
    )
    parser.add_argument(
        "-n",
        "--ngames",
        type=int,
        default=1,
        help="Number of games to be played before exiting. "
        "NetHack will auto-restart if > 1.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=10000,
        help="Number of maximum steps per episode.",
    )
    parser.add_argument(
        "--seeds",
        default=None,
        help="Seeds to send to NetHack. Can be a dict or int. "
        "Defaults to None (no seeding).",
    )
    parser.add_argument(
        "--savedir",
        default="nle_data/play_data",
        help="Directory path where data will be saved. "
        "Defaults to 'nle_data/play_data'.",
    )
    parser.add_argument(
        "--no-render", action="store_true", help="Disables env.render()."
    )
    parser.add_argument(
        "--render_mode",
        type=str,
        default="human",
        choices=["human", "full", "ansi"],
        help="Render mode. Defaults to 'human'.",
    )
    parser.add_argument(
        "--save_gif",
        dest="save_gif",
        action="store_true",
        help="Saving a GIF replay of the evaluated episodes.",
    )
    parser.add_argument(
        "--no-save_gif",
        dest="save_gif",
        action="store_false",
        help="Do not save GIF.",
    )
    parser.set_defaults(save_gif=False)
    parser.add_argument(
        "--gif_path",
        type=str,
        default="replay.gif",
        help="Where to save the produced GIF file.",
    )
    parser.add_argument(
        "--gif_duration",
        type=int,
        default=300,
        help="The duration of each gif image.",
    )
    valid_observations = [
    "glyphs",
    "chars",
    "colors",
    "specials",
    "screen_descriptions",
    "pixel",
    "blstats",
    "message",
    "inv_glyphs",
    "inv_letters",
    "inv_oclasses",
    "inv_strs",
    "tty_chars",
    "tty_colors",
    "tty_cursor",
    "glyphs_crop",
    "chars_crop",
    "colors_crop",
    "specials_crop",
    "pixel_crop",
    "screen_descriptions_crop",
    "tty_chars_crop",
    "tty_colors_crop",
    ]
    parser.add_argument(
        "-o",
        "--dump_observations",
        nargs="+",
        choices=valid_observations,
        default=valid_observations,
        help="Dump observations. Available options: " + ", ".join(valid_observations),
    )
    parser.add_argument(
        "--instruction",
        default="Go down the stairs.",
        help="The instruction to be given to the agent"
    )
    flags = parser.parse_args()

    if flags.debug:
        import ipdb

        cm = ipdb.launch_ipdb_on_exception
    else:
        cm = dummy_context

    with cm():
        if flags.seeds is not None:
            # to handle both int and dicts
            flags.seeds = ast.literal_eval(flags.seeds)

        if flags.savedir == "args":
            flags.savedir = "{}_{}_{}.zip".format(
                time.strftime("%Y%m%d-%H%M%S"), flags.mode, flags.env
            )

        play(**vars(flags))


if __name__ == "__main__":
    main()
