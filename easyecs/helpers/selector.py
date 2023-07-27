from pyfzf import FzfPrompt


def select_action(choices, header, multi=False):
    if not multi:
        try:
            selected_action = FzfPrompt().prompt(
                choices,
                fzf_options=f'--height=10% --border=sharp --header="{header}"',
            )[0]
        except IndexError:
            return None
    else:
        selected_action = FzfPrompt().prompt(
            choices,
            fzf_options=f'--height=10% --border=sharp --multi --header="{header}"',
        )
    return selected_action
