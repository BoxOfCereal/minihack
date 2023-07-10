import jsonlines
import argparse

template_state_string = '''
## STATE AT T: {t}
Goal: {goal}
Blstats: {blstats}
{screen}:
{screen_content}
Inventory:
{inventory}
Message: {message}
Action: {action}

'''

instruction_template_string = '''
# INSTRUCTION:
System Message: {system_message}
Instruction: {instruction}

{current_state}
'''

def generate_template_string(data, last_n_lines, n, screen_type):
    t = data.get("t")
    goal = data.get("goal")
    action = data.get("action")
    blstats = data.get("blstats")
    chars = data.get("chars")
    chars_crop = data.get("chars_crop")
    inventory = data.get("inv_strs")
    message = data.get("message")

    if t is not None:
        if screen_type == 'chars':
            screen = 'Chars'
            screen_content = chars
        else:
            screen = 'Chars Crop'
            screen_content = chars_crop

        current_states = []
        for i, (prev_t, prev_state) in enumerate(last_n_lines):
            if prev_t < t:
                current_states.append(prev_state)

        current_states.append(template_state_string.format(t=t,
                                                            goal=goal,
                                                            action=action,
                                                            blstats=blstats,
                                                            screen=screen,
                                                            screen_content=screen_content,
                                                            inventory="\n".join(inventory),
                                                            message=message))

        last_n_lines.append((t, current_states[-1]))

        if len(last_n_lines) > n:
            last_n_lines.pop(0)

        previous_states = "\n".join(current_states[:-1])
        instruction_template = instruction_template_string.format(system_message=message,
                                                                  instruction="Your instruction here",
                                                                  current_state=previous_states)
        print(f"Instruction template for line:\n{instruction_template}")

        # Assemble complete instruction
        complete_instruction = instruction_template_string.format(system_message=message,
                                                                  instruction="Your complete instruction here",
                                                                  current_state="\n".join(current_states))
        print(f"Complete instruction for line:\n{complete_instruction}")

        return complete_instruction


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Generate instruction templates from a JSON Lines file")
    parser.add_argument("file", type=str, help="Path to the JSON Lines file")
    parser.add_argument("--screen_type", type=str, choices=["chars", "chars_crop"], default="chars_crop",
                        help="Screen type to include in the template")
    parser.add_argument("--output_path", type=str, default="./output.jsonl",
                        help="Output path for the new JSON Lines file")
    args = parser.parse_args()

    # Load JSON Lines file and generate instructions
    filename = args.file
    output_path = args.output_path
    screen_type = args.screen_type
    n = 6  # Number of previous states to include in the instruction template
    last_n_lines = []
    instructions = []

    with jsonlines.open(filename, "r") as reader:
        for data in reader:
            instruction = generate_template_string(data, last_n_lines, n, screen_type)
            instructions.append(instruction)

    # Write instructions to a new JSON Lines file
    with jsonlines.open(output_path, "w") as writer:
        writer.write_all(instructions)

    print(f"Instructions written to: {output_path}")
