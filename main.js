// MineVideo - behavior pack script
// Hold a Clock and use it (right click / tap) to open the video menu.
import { world, system } from "@minecraft/server";
import { ActionFormData } from "@minecraft/server-ui";
import { VIDEO } from "./config.js";

const SIZES = [
  { name: "Small", event: "vid:size_s", dist: 3 },
  { name: "Medium", event: "vid:size_m", dist: 5 },
  { name: "Large", event: "vid:size_l", dist: 8 },
  { name: "Huge", event: "vid:size_xl", dist: 12 },
];

function sizeIndex(player) {
  const v = player.getDynamicProperty("vid:size");
  return typeof v === "number" && v >= 0 && v < SIZES.length ? v : 1;
}

function screensNear(player, radius) {
  return player.dimension.getEntities({
    type: "vid:screen",
    location: player.location,
    maxDistance: radius,
  });
}

function removeScreens(player) {
  let count = 0;
  for (const e of screensNear(player, 128)) {
    e.remove();
    count++;
  }
  return count;
}

function placeScreen(player, at, yaw) {
  const sz = SIZES[sizeIndex(player)];
  let loc = at;
  let rot = yaw;
  if (!loc) {
    const head = player.getHeadLocation();
    const dir = player.getViewDirection();
    const len = Math.sqrt(dir.x * dir.x + dir.z * dir.z) || 1;
    loc = {
      x: head.x + (dir.x / len) * sz.dist,
      y: head.y + sz.dist * 0.15,
      z: head.z + (dir.z / len) * sz.dist,
    };
    rot = player.getRotation().y;
  }
  const screen = player.dimension.spawnEntity("vid:screen", loc);
  screen.setRotation({ x: 0, y: rot });
  screen.triggerEvent(sz.event);
  return screen;
}

function restartNearest(player) {
  const list = screensNear(player, 128);
  if (list.length === 0) {
    player.sendMessage("No screen nearby. Choose Play here first.");
    return;
  }
  let best = list[0];
  let bestD = Infinity;
  for (const e of list) {
    const dx = e.location.x - player.location.x;
    const dz = e.location.z - player.location.z;
    const d = dx * dx + dz * dz;
    if (d < bestD) {
      bestD = d;
      best = e;
    }
  }
  const loc = { x: best.location.x, y: best.location.y, z: best.location.z };
  const yaw = best.getRotation().y;
  best.remove();
  system.run(() => placeScreen(player, loc, yaw));
}

function openMenu(player) {
  const sz = SIZES[sizeIndex(player)];
  const info =
    "Video: " + VIDEO.title +
    "\nLength: " + VIDEO.seconds + " s   Frames: " + VIDEO.frames + " @ " + VIDEO.fps + " fps" +
    "\nPicture: " + VIDEO.width + "x" + VIDEO.height +
    "\nSound: " + (VIDEO.audio ? "yes" : "no") +
    "\nScreen size: " + sz.name;
  const form = new ActionFormData()
    .title("Mine Video")
    .body(info)
    .button("Play here")
    .button("Restart nearest screen")
    .button("Remove screens")
    .button("Size: " + sz.name + " (tap to change)");
  form.show(player).then((r) => {
    if (r.canceled) return;
    if (r.selection === 0) {
      system.run(() => {
        removeScreens(player);
        placeScreen(player);
      });
    } else if (r.selection === 1) {
      system.run(() => restartNearest(player));
    } else if (r.selection === 2) {
      system.run(() => {
        const n = removeScreens(player);
        player.sendMessage("Removed " + n + " screen(s).");
      });
    } else if (r.selection === 3) {
      const next = (sizeIndex(player) + 1) % SIZES.length;
      player.setDynamicProperty("vid:size", next);
      player.sendMessage("Screen size: " + SIZES[next].name);
      system.run(() => openMenu(player));
    }
  });
}

world.afterEvents.itemUse.subscribe((ev) => {
  const item = ev.itemStack;
  if (!item || item.typeId !== "minecraft:clock") return;
  system.run(() => openMenu(ev.source));
});
