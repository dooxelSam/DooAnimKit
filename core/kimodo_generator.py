"""
Procedural In-Place Locomotion & Semantic Motion Generator for DooAnimKit.
Generates native Maya ASCII (.ma) humanoid joint animations.
"""

import sys
import os
import argparse
import math


def _generate_in_place_motion(prompt, frames, fps):
    """Calculates procedural curves for In-Place Walk, Run, Jump, and Idle."""
    p = prompt.lower()
    
    # Визначення режиму руху
    is_run = "run" in p or "sprint" in p or "fast" in p
    is_jump = "jump" in p or "leap" in p
    is_idle = "idle" in p or "stand" in p or "wait" in p
    
    speed = 2.0 if is_run else 1.0
    freq = (speed * 2.0 * math.pi) / float(fps)
    
    curves = {
        ("Hips", "ty", "animCurveTL"): [],
        ("Hips", "rx", "animCurveTA"): [],
        ("Hips", "ry", "animCurveTA"): [],
        ("Hips", "rz", "animCurveTA"): [],
        ("Spine", "rx", "animCurveTA"): [],
        ("LeftUpLeg", "rx", "animCurveTA"): [],
        ("RightUpLeg", "rx", "animCurveTA"): [],
        ("LeftLeg", "rx", "animCurveTA"): [],
        ("RightLeg", "rx", "animCurveTA"): [],
        ("LeftArm", "rx", "animCurveTA"): [],
        ("RightArm", "rx", "animCurveTA"): [],
        ("LeftForeArm", "rx", "animCurveTA"): [],
        ("RightForeArm", "rx", "animCurveTA"): []
    }

    for f in range(frames):
        t = f * freq

        if is_idle:
            # Спокійне дихання та зміщення ваги
            t_idle = f * (1.0 * math.pi) / float(fps)
            hips_y = 95.0 + math.sin(t_idle) * 0.8
            spine_rx = math.sin(t_idle) * 2.0
            curves[("Hips", "ty", "animCurveTL")].append(hips_y)
            curves[("Hips", "rx", "animCurveTA")].append(0.0)
            curves[("Hips", "ry", "animCurveTA")].append(0.0)
            curves[("Hips", "rz", "animCurveTA")].append(math.sin(t_idle * 0.5) * 1.5)
            curves[("Spine", "rx", "animCurveTA")].append(spine_rx)
            curves[("LeftUpLeg", "rx", "animCurveTA")].append(0.0)
            curves[("RightUpLeg", "rx", "animCurveTA")].append(0.0)
            curves[("LeftLeg", "rx", "animCurveTA")].append(0.0)
            curves[("RightLeg", "rx", "animCurveTA")].append(0.0)
            curves[("LeftArm", "rx", "animCurveTA")].append(5.0 + math.sin(t_idle) * 1.5)
            curves[("RightArm", "rx", "animCurveTA")].append(5.0 + math.sin(t_idle) * 1.5)
            curves[("LeftForeArm", "rx", "animCurveTA")].append(10.0)
            curves[("RightForeArm", "rx", "animCurveTA")].append(10.0)

        elif is_jump:
            # Фазовий стрибок (цикл на 60 кадрів)
            cycle_f = f % 60
            if cycle_f < 15:  # Crouch / Anticipation
                factor = cycle_f / 15.0
                hips_y = 95.0 - (factor * 25.0)
                leg_rx = factor * 40.0
                knee_rx = factor * 60.0
                arm_rx = -factor * 30.0
            elif cycle_f < 35:  # Air phase
                factor = (cycle_f - 15) / 20.0
                hips_y = 70.0 + math.sin(factor * math.pi) * 50.0
                leg_rx = -15.0
                knee_rx = 20.0
                arm_rx = 45.0
            else:  # Landing / Recovery
                factor = (cycle_f - 35) / 25.0
                hips_y = 95.0 - (math.sin(factor * math.pi) * 15.0)
                leg_rx = math.sin(factor * math.pi) * 20.0
                knee_rx = math.sin(factor * math.pi) * 35.0
                arm_rx = 0.0

            curves[("Hips", "ty", "animCurveTL")].append(hips_y)
            curves[("Hips", "rx", "animCurveTA")].append(leg_rx * 0.3)
            curves[("Hips", "ry", "animCurveTA")].append(0.0)
            curves[("Hips", "rz", "animCurveTA")].append(0.0)
            curves[("Spine", "rx", "animCurveTA")].append(-leg_rx * 0.4)
            curves[("LeftUpLeg", "rx", "animCurveTA")].append(leg_rx)
            curves[("RightUpLeg", "rx", "animCurveTA")].append(leg_rx)
            curves[("LeftLeg", "rx", "animCurveTA")].append(knee_rx)
            curves[("RightLeg", "rx", "animCurveTA")].append(knee_rx)
            curves[("LeftArm", "rx", "animCurveTA")].append(arm_rx)
            curves[("RightArm", "rx", "animCurveTA")].append(arm_rx)
            curves[("LeftForeArm", "rx", "animCurveTA")].append(knee_rx * 0.5)
            curves[("RightForeArm", "rx", "animCurveTA")].append(knee_rx * 0.5)

        else:
            # Стандартний In-Place Walk / Run
            stride = 45.0 if is_run else 28.0
            bounce = 5.5 if is_run else 3.0
            arm_swing = 40.0 if is_run else 22.0

            hips_y = 95.0 - abs(math.sin(t)) * bounce
            curves[("Hips", "ty", "animCurveTL")].append(hips_y)
            curves[("Hips", "rx", "animCurveTA")].append(math.sin(t) * 2.0)
            curves[("Hips", "ry", "animCurveTA")].append(math.sin(t) * 5.0)
            curves[("Hips", "rz", "animCurveTA")].append(math.cos(t) * 2.0)
            curves[("Spine", "rx", "animCurveTA")].append(math.sin(t) * 3.0)

            # Протифазний рух стегон та колін
            curves[("LeftUpLeg", "rx", "animCurveTA")].append(math.sin(t) * stride)
            curves[("RightUpLeg", "rx", "animCurveTA")].append(-math.sin(t) * stride)
            curves[("LeftLeg", "rx", "animCurveTA")].append(max(0.0, math.sin(t - 1.2) * (stride * 1.4)))
            curves[("RightLeg", "rx", "animCurveTA")].append(max(0.0, -math.sin(t - 1.2) * (stride * 1.4)))

            # Руки в протифазі до ніг
            curves[("LeftArm", "rx", "animCurveTA")].append(-math.sin(t) * arm_swing)
            curves[("RightArm", "rx", "animCurveTA")].append(math.sin(t) * arm_swing)
            curves[("LeftForeArm", "rx", "animCurveTA")].append(max(5.0, -math.sin(t) * arm_swing + 15.0))
            curves[("RightForeArm", "rx", "animCurveTA")].append(max(5.0, math.sin(t) * arm_swing + 15.0))

    return curves


def generate_motion_ma(prompt, frames, fps, output_path):
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    joints = [
        ("Hips", None, (0, 95, 0)),
        ("Spine", "Hips", (0, 15, 0)),
        ("Spine1", "Spine", (0, 15, 0)),
        ("Chest", "Spine1", (0, 15, 0)),
        ("Neck", "Chest", (0, 10, 0)),
        ("Head", "Neck", (0, 10, 0)),
        ("LeftShoulder", "Chest", (12, 10, 0)),
        ("LeftArm", "LeftShoulder", (15, 0, 0)),
        ("LeftForeArm", "LeftArm", (25, 0, 0)),
        ("LeftHand", "LeftForeArm", (20, 0, 0)),
        ("RightShoulder", "Chest", (-12, 10, 0)),
        ("RightArm", "RightShoulder", (-15, 0, 0)),
        ("RightForeArm", "RightArm", (-25, 0, 0)),
        ("RightHand", "RightForeArm", (-20, 0, 0)),
        ("LeftUpLeg", "Hips", (10, -5, 0)),
        ("LeftLeg", "LeftUpLeg", (0, -42, 0)),
        ("LeftFoot", "LeftLeg", (0, -42, 5)),
        ("RightUpLeg", "Hips", (-10, -5, 0)),
        ("RightLeg", "RightUpLeg", (0, -42, 0)),
        ("RightFoot", "RightLeg", (0, -42, 5)),
    ]

    lines = [
        "//Maya ASCII 2022 scene",
        f"//Generated by DooAnimKit In-Place Motion Generator. Prompt: {prompt}",
        "requires maya \"2022\";",
        f"currentUnit -l centimeter -a degree -t {fps}fps;",
    ]

    for name, parent, (tx, ty, tz) in joints:
        p_flag = f"-p \"{parent}\"" if parent else ""
        lines.append(f"createNode joint -n \"{name}\" {p_flag};")
        lines.append(f"\tsetAttr \".t\" -type \"double3\" {tx} {ty} {tz};")

    curves_data = _generate_in_place_motion(prompt, frames, fps)

    curve_idx = 0
    for (node, attr, c_type), vals in curves_data.items():
        c_name = f"kimodo_anim_{curve_idx}"
        lines.append(f"createNode {c_type} -n \"{c_name}\";")
        lines.append(f"\tsetAttr -s {frames} \".ktv[0:{frames-1}]\" " + " ".join(f"{f+1} {vals[f]:.3f}" for f in range(frames)) + ";")
        lines.append(f"connectAttr \"{c_name}.o\" \"{node}.{attr}\";")
        curve_idx += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--output", type=str, required=True)

    args = parser.parse_args()
    generate_motion_ma(args.prompt, args.frames, args.fps, args.output)
    sys.exit(0)