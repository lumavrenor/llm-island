"""
癒し：救助判定（2026-10-13 に power.py から置き換え）

- フリーズした住人の近くに「手の空いた」ヒーラーが来たら、救助判断（癒すかどうか）の待ちにする
  （1 体のフリーズ住人につき、判断・詠唱しているヒーラーは 1 体だけ）。
  フリーズを解けるのはヒーラーの杖だけなので、普通の住人は救助判断をしない
- 癒すと決めたあとの詠唱（casting）と目覚めは World.start_heal() / finish_heal()
- solace（心の回復）は場所に入っているだけで効くので、ここではなく Npc._recover() で見る
"""

from __future__ import annotations


def check_rescues(world):
    """手の空いたヒーラーがフリーズ住人のそばにいたら、救助判断の待ちにする"""
    nc = world.cfg.npc
    frozen = [n for n in world.npcs if n.frozen and n.rescuer is None]
    if not frozen:
        return
    for npc in world.npcs:
        if not npc.healer or not npc.free:
            continue
        for s in frozen:
            if s.rescuer is not None or npc.dist_to(s) > nc.rescue_radius:
                continue
            if world.now < world.rescue_cooldown.get((npc.id, s.id), 0.0):
                continue
            npc.rescue_target = s.id
            s.rescuer = npc.id
            npc.face(s)
            npc.state.change("idle")
            world.emit("rescue_check", npc=npc.id, target=s.id)
            break
