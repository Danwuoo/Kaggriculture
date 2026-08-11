"""Kaggle entrypoint. Runtime imports are sibling modules in the archive root."""

from controller import Controller
from state import generic_safe_action


_controllers = {}


def agent(obs):
    try:
        player = int(obs.get("player", 0))
    except Exception:
        player = 0
    try:
        controller = _controllers.get(player)
        if controller is None:
            controller = Controller(player)
            _controllers[player] = controller
        return controller.act(obs)
    except Exception:
        return generic_safe_action(obs)

