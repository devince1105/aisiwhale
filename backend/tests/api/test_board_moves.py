"""AD-08: the production board offers only moves a person may make, and the API refuses the
rest. The board's moves are one table (frontend/web/src/features/board/moves.json); every one
must be a way the state machine allows, and a card moved from the wrong state is refused."""

import json
from pathlib import Path

import pytest

from autora.domains.newsroom.articles import ARTICLE_FSM
from autora.domains.newsroom.stories import STORY_FSM

MOVES = json.loads(
    (Path(__file__).parents[3] / "frontend/web/src/features/board/moves.json").read_text()
)


@pytest.mark.parametrize(("from_state", "to_state", "action"), MOVES["article"])
def test_every_article_move_is_one_the_state_machine_allows(from_state, to_state, action):
    assert ARTICLE_FSM.can(from_state, to_state), f"{action}: {from_state} → {to_state}"


@pytest.mark.parametrize(("from_state", "to_state", "action"), MOVES["story"])
def test_every_story_move_is_a_way_the_state_machine_allows(from_state, to_state, action):
    # 開始製作 selects a story first if it was only found, then starts it: a way, not one step
    assert STORY_FSM.shortest_path(from_state, to_state)[-1] == to_state, action


def test_the_board_names_only_real_states():
    for entity, fsm in (("article", ARTICLE_FSM), ("story", STORY_FSM)):
        for from_state, to_state, _ in MOVES[entity]:
            fsm.states(from_state), fsm.states(to_state)  # raises on a name it does not know


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("unpublish", {"reason": "x"}),
        ("republish", None),
        ("revise", {"reason": "x"}),
    ],
)
async def test_a_draft_dragged_where_it_may_not_go_is_refused(api, newsroom_room, path, body):
    """A card the board would not let go of, sent anyway (an old page, a script): 409."""
    room = newsroom_room
    drafted = await room.call("write_draft", room.draft(list(room.claims.values())))
    article_id = drafted.output["article_id"]
    response = await api.post(f"/api/articles/{article_id}/{path}", json=body)
    assert response.status_code == 409, response.text
