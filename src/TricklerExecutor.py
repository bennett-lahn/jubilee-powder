"""Static trickler fill execution logic used by MovementExecutor."""

import logging
import threading
import time

from typing import Callable

from src.ConfigLoader import config as _system_config
from src.Scale import Scale

logger = logging.getLogger(__name__)


class TricklerExecutor:
    """Encapsulates trickler fill behavior as static helper methods."""

    @staticmethod
    def _set_trickler_vibration(machine, amplitude: float) -> None:
        """Set trickler vibration servo amplitude (M42 P0)."""
        machine.gcode(f"M42 P0 S{amplitude:.2f} F20000")

    @staticmethod
    def _auto_recover_jam(
        machine,
        open_cover: Callable[[], bool],
        close_cover: Callable[[], bool],
        vibration_amplitude: float,
        wait_seconds: float,
    ) -> None:
        """First jam in a fill iteration: cycle cover, bump vibration, and retry."""
        logger.warning(
            "[Jam] Powder jam detected - auto-recovery: close/reopen cover, "
            "vibration %.2f for %.0fs",
            vibration_amplitude,
            wait_seconds,
        )
        try:
            TricklerExecutor._set_trickler_vibration(machine, 0.0)
            machine.gcode("M400")
        except Exception as e:
            logger.warning("[Jam] Could not stop vibration before cover cycle: %s", e)

        if not close_cover():
            logger.warning(
                "[Jam] Failed to close powder dispenser cover during auto-recovery"
            )
        if not open_cover():
            logger.warning(
                "[Jam] Failed to reopen powder dispenser cover during auto-recovery"
            )

        try:
            TricklerExecutor._set_trickler_vibration(machine, vibration_amplitude)
            machine.gcode("M400")
        except Exception as e:
            logger.warning("[Jam] Could not set recovery vibration: %s", e)
        time.sleep(wait_seconds)
        TricklerExecutor._set_trickler_vibration(machine, 0.0)
        logger.info("[Jam] Auto-recovery complete - resuming dispensing.")

    @staticmethod
    def _handle_jam(
        machine,
        jam_resume_event: threading.Event,
        on_jam_detected: Callable | None,
    ) -> None:
        """Block dispensing until clear_jam is called after operator intervention."""
        try:
            TricklerExecutor._set_trickler_vibration(machine, 0.0)
            machine.gcode("M400")
        except Exception as e:
            logger.warning("[Jam] Could not stop vibration: %s", e)

        jam_resume_event.clear()
        logger.warning("[Jam] Powder jam detected - waiting for operator clearance.")

        if on_jam_detected is not None:
            try:
                on_jam_detected()
            except Exception as e:
                logger.warning("[Jam] on_jam_detected callback raised: %s", e)

        jam_resume_event.wait()
        logger.info("[Jam] Jam cleared by operator - resuming dispensing.")

    @staticmethod
    def _recover_from_jam_stall(
        machine,
        jam_resume_event: threading.Event,
        on_jam_detected: Callable | None,
        open_cover: Callable[[], bool],
        close_cover: Callable[[], bool],
        *,
        jam_auto_recovered: bool,
        recovery_vib_amp: float,
        recovery_wait_seconds: float,
    ) -> bool:
        """Handle a detected jam stall and return updated recovery state."""
        if not jam_auto_recovered:
            TricklerExecutor._auto_recover_jam(
                machine,
                open_cover,
                close_cover,
                recovery_vib_amp,
                recovery_wait_seconds,
            )
            return True
        TricklerExecutor._handle_jam(machine, jam_resume_event, on_jam_detected)
        return True

    @staticmethod
    def execute_fill_powder(
        machine,
        scale: Scale,
        target_weight: float,
        jam_resume_event: threading.Event,
        on_jam_detected: Callable | None,
        open_cover: Callable[[], bool],
        close_cover: Callable[[], bool],
    ) -> tuple[bool, float | None]:
        """Fill the mold on the scale using the trickler."""
        trickler = _system_config.get_active_trickler_profile()

        flow_alpha = trickler.flow_ema_alpha
        yield_alpha = trickler.yield_ema_alpha
        jam_threshold = trickler.jam_yield_threshold
        jam_iter_limit = trickler.jam_iter_threshold
        jam_recovery_vib_amp = trickler.jam_auto_recovery_vibration_amplitude
        jam_recovery_wait_seconds = trickler.jam_auto_recovery_wait_seconds
        max_step = trickler.max_step_size_mm
        min_step = trickler.min_step_size_mm
        warmup_steps = trickler.warmup_steps
        warmup_max_step = trickler.warmup_max_step_mm
        coarse_pct = trickler.coarse_threshold_pct
        finish_pct = trickler.finish_threshold_pct
        coarse_tgt_steps = trickler.coarse_target_steps
        coarse_feedrate = trickler.coarse_feedrate
        fine_feedrate = trickler.fine_feedrate
        coarse_vib_amp = trickler.coarse_vibration_amplitude
        fine_vib_amp = trickler.fine_vibration_amplitude
        max_dribble_step = trickler.max_dribble_step_mm

        coarse_feedrate_str = f"F{coarse_feedrate}"
        fine_feedrate_str = f"F{fine_feedrate}"
        coarse_threshold = coarse_pct * target_weight
        finish_threshold = finish_pct * target_weight

        try:
            machine.gcode("M400")
            if not open_cover():
                raise RuntimeError("Failed to open powder dispenser cover servo")

            initial_weight = scale.get_weight(stable=True)
            logger.info("[Fill] Initial weight at start of fill: %.4fg", initial_weight)
            logger.info(
                "[Fill] Target: %.4fg coarse: %.4fg finish: %.4fg",
                target_weight,
                coarse_threshold,
                finish_threshold,
            )

            machine.gcode("G92 W0")
            machine.gcode("G91")

            current_vib_amp = coarse_vib_amp
            TricklerExecutor._set_trickler_vibration(machine, current_vib_amp)

            flow_ema = 0.0
            yield_ema = 0.0
            step_count = 0
            stagnant_count = 0
            motor_has_moved = False
            threshold_crossed = False
            jam_auto_recovered = False
            final_weight: float | None = None

            while True:
                if threshold_crossed:
                    time.sleep(0.15)
                    current_weight = scale.get_weight(stable=True)
                    logger.debug("[FillTrace] stable sample: weight=%.4f", current_weight)
                else:
                    current_weight = scale.get_weight(stable=False)
                    logger.debug("[FillTrace] unstable sample: weight=%.4f", current_weight)

                if current_weight >= coarse_threshold:
                    if not threshold_crossed:
                        threshold_crossed = True
                        current_vib_amp = fine_vib_amp
                        logger.info(
                            "[Fill] Coarse threshold crossed at %.4fg", current_weight
                        )
                        TricklerExecutor._set_trickler_vibration(machine, current_vib_amp)
                        time.sleep(0.15)
                        current_weight = scale.get_weight(stable=True)
                        logger.debug(
                            "[FillTrace] stable sample after coarse crossing: weight=%.4f",
                            current_weight,
                        )

                    remaining = max(0.0, finish_threshold - current_weight)
                    if yield_ema > 0 and remaining > 0:
                        step_size = remaining / yield_ema
                    else:
                        step_size = min_step
                    step_size = max(min_step, min(max_dribble_step, step_size))

                    weight_before_step = current_weight
                    machine.gcode(f"G1 W{step_size:.4f} {fine_feedrate_str}")
                    machine.gcode("M400")
                    motor_has_moved = True

                    weight_after_step = scale.get_weight(stable=True)
                    logger.debug(
                        "[FillTrace] stable sample after fine step: weight=%.4f",
                        weight_after_step,
                    )
                    weight_gained = max(0.0, weight_after_step - weight_before_step)
                    step_yield = weight_gained / step_size

                    flow_ema = flow_alpha * step_yield + (1 - flow_alpha) * flow_ema
                    yield_ema = yield_alpha * step_yield + (1 - yield_alpha) * yield_ema
                    step_count += 1

                    if flow_ema < jam_threshold:
                        stagnant_count += 1
                    else:
                        stagnant_count = 0
                    if stagnant_count >= jam_iter_limit:
                        jam_auto_recovered = TricklerExecutor._recover_from_jam_stall(
                            machine,
                            jam_resume_event,
                            on_jam_detected,
                            open_cover,
                            close_cover,
                            jam_auto_recovered=jam_auto_recovered,
                            recovery_vib_amp=jam_recovery_vib_amp,
                            recovery_wait_seconds=jam_recovery_wait_seconds,
                        )
                        stagnant_count = 0
                        flow_ema = 0.0
                        yield_ema = 0.0
                        TricklerExecutor._set_trickler_vibration(machine, current_vib_amp)
                        continue

                    current_weight = weight_after_step

                    if current_weight >= finish_threshold:
                        TricklerExecutor._set_trickler_vibration(machine, 0.0)
                        time.sleep(4)
                        final_weight = scale.get_weight(stable=True)
                        logger.info("[Fill] Stable confirmation: %.4fg", final_weight)
                        if final_weight >= finish_threshold:
                            logger.info("[Fill] Target reached: %.4fg", final_weight)
                            break
                        logger.info(
                            "[Fill] Stable weight %.4fg below threshold, continuing...",
                            final_weight,
                        )
                        TricklerExecutor._set_trickler_vibration(machine, current_vib_amp)

                else:
                    if step_count < warmup_steps or yield_ema == 0.0:
                        progress = max(0.0, current_weight / coarse_threshold)
                        step_size = max_step - (max_step - min_step) * progress
                        step_size = min(
                            step_size,
                            warmup_max_step if step_count < warmup_steps else max_step,
                        )
                    else:
                        target_remaining = coarse_threshold - current_weight
                        step_size = target_remaining / (yield_ema * coarse_tgt_steps)
                        step_size = max(min_step, min(max_step, step_size))

                    weight_before_step = current_weight
                    machine.gcode(f"G1 W{step_size:.4f} {coarse_feedrate_str}")
                    machine.gcode("M400")
                    motor_has_moved = True

                    weight_after_step = scale.get_weight(stable=False)
                    weight_gained = max(0.0, weight_after_step - weight_before_step)
                    step_yield = weight_gained / step_size

                    flow_ema = flow_alpha * step_yield + (1 - flow_alpha) * flow_ema
                    yield_ema = yield_alpha * step_yield + (1 - yield_alpha) * yield_ema
                    step_count += 1

                    if motor_has_moved and step_count > warmup_steps:
                        if flow_ema < jam_threshold:
                            stagnant_count += 1
                        else:
                            stagnant_count = 0
                        if stagnant_count >= jam_iter_limit:
                            jam_auto_recovered = TricklerExecutor._recover_from_jam_stall(
                                machine,
                                jam_resume_event,
                                on_jam_detected,
                                open_cover,
                                close_cover,
                                jam_auto_recovered=jam_auto_recovered,
                                recovery_vib_amp=jam_recovery_vib_amp,
                                recovery_wait_seconds=jam_recovery_wait_seconds,
                            )
                            stagnant_count = 0
                            flow_ema = 0.0
                            yield_ema = 0.0
                            TricklerExecutor._set_trickler_vibration(
                                machine, current_vib_amp
                            )
                            continue

            return True, final_weight

        except Exception as e:
            logger.error("[Fill] Error filling mold with powder: %s", e)
            return False, None
        finally:
            try:
                TricklerExecutor._set_trickler_vibration(machine, 0.0)
                machine.gcode("G90")
            except Exception:
                pass
            if not close_cover():
                logger.warning("Failed to close powder dispenser cover servo")
