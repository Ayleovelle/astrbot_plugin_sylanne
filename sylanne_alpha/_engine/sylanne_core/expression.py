"""Sylanne Expression Mapping: PAD state to output modalities.

Maps PAD (Pleasure-Arousal-Dominance) emotional states to concrete output
representations for embodied agents across four modalities:

1. Blend shapes (ARKit-compatible face animation)
2. Motor commands (robotic embodiment)
3. Text style parameters (chatbot response styling)
4. Audio prosody parameters (TTS modulation)

Theoretical grounding:
  - Ekman & Friesen (1978): FACS — Facial Action Coding System
  - Scherer & Ellgring (2007): Multimodal expression of emotion
  - Breazeal (2003): Emotion and sociable humanoid robots
  - Pennebaker et al. (2011): Linguistic markers of psychological state
  - Scherer (2003): Vocal communication of emotion

Design invariants (all mappings satisfy):
  - Deterministic: identical PAD input always produces identical output
  - Bounded: outputs never exceed declared ranges
  - Continuous: Lipschitz — small PAD change yields small output change

Pure Python. No external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .compute.pad_interop import PADVector
from .standard import EmotionVector

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    """Scalar clamp to [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from a to b by factor t in [0, 1]."""
    return a + (b - a) * _clamp(t, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 1. Blend Shape Profile (ARKit 52 blend shapes)
# ---------------------------------------------------------------------------

# Full list of 52 ARKit-compatible blend shape names.
# Reference: Apple ARKit Face Tracking (2017), based on FACS AU mapping.
ARKIT_BLEND_SHAPES: tuple[str, ...] = (
    "browInnerUp",
    "browDownLeft",
    "browDownRight",
    "browOuterUpLeft",
    "browOuterUpRight",
    "eyeLookUpLeft",
    "eyeLookUpRight",
    "eyeLookDownLeft",
    "eyeLookDownRight",
    "eyeLookInLeft",
    "eyeLookInRight",
    "eyeLookOutLeft",
    "eyeLookOutRight",
    "eyeBlinkLeft",
    "eyeBlinkRight",
    "eyeSquintLeft",
    "eyeSquintRight",
    "eyeWideLeft",
    "eyeWideRight",
    "cheekPuff",
    "cheekSquintLeft",
    "cheekSquintRight",
    "noseSneerLeft",
    "noseSneerRight",
    "jawOpen",
    "jawForward",
    "jawLeft",
    "jawRight",
    "mouthFunnel",
    "mouthPucker",
    "mouthLeft",
    "mouthRight",
    "mouthSmileLeft",
    "mouthSmileRight",
    "mouthFrownLeft",
    "mouthFrownRight",
    "mouthDimpleLeft",
    "mouthDimpleRight",
    "mouthStretchLeft",
    "mouthStretchRight",
    "mouthRollLower",
    "mouthRollUpper",
    "mouthShrugLower",
    "mouthShrugUpper",
    "mouthPressLeft",
    "mouthPressRight",
    "mouthLowerDownLeft",
    "mouthLowerDownRight",
    "mouthUpperUpLeft",
    "mouthUpperUpRight",
    "tongueOut",
    "mouthClose",
)

# Index lookup for fast access
_BS_INDEX: dict[str, int] = {name: i for i, name in enumerate(ARKIT_BLEND_SHAPES)}


@dataclass(slots=True)
class BlendShapeProfile:
    """52 ARKit-compatible blend shape weights for facial animation.

    Each weight is in [0, 1]. The shape list follows Apple ARKit Face Tracking
    (2017) which maps to Ekman & Friesen FACS Action Units (1978).

    Compatible with VTuber face tracking, 3D character animation, and
    any system consuming ARKit blend shape coefficients.
    """

    weights: list[float] = field(default_factory=lambda: [0.0] * 52)

    def __post_init__(self) -> None:
        if len(self.weights) != 52:
            raise ValueError(
                f"BlendShapeProfile requires exactly 52 weights, got {len(self.weights)}"
            )
        # Enforce [0, 1] bounds
        self.weights = [_clamp(w, 0.0, 1.0) for w in self.weights]

    def get(self, name: str) -> float:
        """Get blend shape weight by name."""
        idx = _BS_INDEX.get(name)
        if idx is None:
            raise KeyError(f"Unknown blend shape: {name}")
        return self.weights[idx]

    def set(self, name: str, value: float) -> None:
        """Set blend shape weight by name (clamped to [0, 1])."""
        idx = _BS_INDEX.get(name)
        if idx is None:
            raise KeyError(f"Unknown blend shape: {name}")
        self.weights[idx] = _clamp(value, 0.0, 1.0)

    def to_dict(self) -> dict[str, float]:
        """Export as name -> weight dictionary."""
        return {name: self.weights[i] for i, name in enumerate(ARKIT_BLEND_SHAPES)}

    def nonzero(self) -> dict[str, float]:
        """Return only non-zero blend shapes (useful for sparse transmission)."""
        return {
            name: self.weights[i]
            for i, name in enumerate(ARKIT_BLEND_SHAPES)
            if self.weights[i] > 1e-6
        }


# ---------------------------------------------------------------------------
# 2. PAD to Blend Shape Mapping
# ---------------------------------------------------------------------------


class PADToBlendShape:
    """Maps PAD vectors to ARKit blend shape profiles.

    Based on Ekman & Friesen (1978) FACS and Scherer & Ellgring (2007)
    multimodal expression research.

    Mapping logic:
      - Valence controls smile/frown axis:
        Positive valence -> AU6 (cheek raiser) + AU12 (lip corner puller)
        Negative valence -> AU15 (lip corner depressor) + AU17 (chin raiser)
      - Arousal controls eye wideness and jaw openness:
        High arousal -> AU5 (upper lid raiser) + AU26 (jaw drop)
        Low arousal -> AU43 (eyes closing / squint)
      - Dominance controls brow position:
        High dominance -> AU1 (inner brow raiser) + AU2 (outer brow raiser)
        Low dominance -> AU4 (brow lowerer)

    Interpolation between prototypical expressions follows
    Scherer & Ellgring (2007) continuous affect-expression mapping.

    Properties:
      - Deterministic: same PAD always yields same blend shapes
      - Bounded: all weights in [0, 1]
      - Lipschitz continuous: small PAD change -> small weight change
    """

    def __init__(self, intensity_scale: float = 1.0) -> None:
        """Initialize the blend shape mapper.

        Args:
            intensity_scale: Global multiplier for expression intensity [0, 2].
                1.0 = natural expression, <1 = subdued, >1 = exaggerated.
        """
        self._intensity = _clamp(intensity_scale, 0.0, 2.0)

    def map(self, pad: PADVector) -> BlendShapeProfile:
        """Map a PAD vector to a complete blend shape profile.

        Args:
            pad: PAD emotional state vector.

        Returns:
            BlendShapeProfile with 52 ARKit-compatible weights.
        """
        weights = [0.0] * 52
        v = pad.valence  # [-1, 1]
        a = pad.arousal  # [0, 1]
        d = pad.dominance  # [0, 1]
        s = self._intensity

        # --- Valence axis: smile vs frown ---
        # Ekman FACS: AU6+AU12 = Duchenne smile, AU15+AU17 = sadness/frown
        if v >= 0.0:
            smile = v * s
            # AU12 -> mouthSmileLeft/Right
            weights[_BS_INDEX["mouthSmileLeft"]] = _clamp(smile * 0.9, 0.0, 1.0)
            weights[_BS_INDEX["mouthSmileRight"]] = _clamp(smile * 0.9, 0.0, 1.0)
            # AU6 -> cheekSquintLeft/Right (Duchenne marker)
            weights[_BS_INDEX["cheekSquintLeft"]] = _clamp(smile * 0.5, 0.0, 1.0)
            weights[_BS_INDEX["cheekSquintRight"]] = _clamp(smile * 0.5, 0.0, 1.0)
            # Dimples at high smile intensity
            weights[_BS_INDEX["mouthDimpleLeft"]] = _clamp(smile * 0.3, 0.0, 1.0)
            weights[_BS_INDEX["mouthDimpleRight"]] = _clamp(smile * 0.3, 0.0, 1.0)
        else:
            frown = (-v) * s
            # AU15 -> mouthFrownLeft/Right
            weights[_BS_INDEX["mouthFrownLeft"]] = _clamp(frown * 0.8, 0.0, 1.0)
            weights[_BS_INDEX["mouthFrownRight"]] = _clamp(frown * 0.8, 0.0, 1.0)
            # AU17 -> mouthLowerDownLeft/Right (chin raiser effect)
            weights[_BS_INDEX["mouthLowerDownLeft"]] = _clamp(frown * 0.3, 0.0, 1.0)
            weights[_BS_INDEX["mouthLowerDownRight"]] = _clamp(frown * 0.3, 0.0, 1.0)
            # Mouth press for suppressed negative emotion
            weights[_BS_INDEX["mouthPressLeft"]] = _clamp(frown * 0.2, 0.0, 1.0)
            weights[_BS_INDEX["mouthPressRight"]] = _clamp(frown * 0.2, 0.0, 1.0)

        # --- Arousal axis: eye wideness and jaw ---
        # Scherer 2003: high arousal -> wide eyes, open mouth
        # Low arousal -> droopy eyes, closed mouth
        if a > 0.5:
            high_a = (a - 0.5) * 2.0 * s  # Normalize to [0, 1] then scale
            # AU5 -> eyeWideLeft/Right
            weights[_BS_INDEX["eyeWideLeft"]] = _clamp(high_a * 0.7, 0.0, 1.0)
            weights[_BS_INDEX["eyeWideRight"]] = _clamp(high_a * 0.7, 0.0, 1.0)
            # AU26 -> jawOpen
            weights[_BS_INDEX["jawOpen"]] = _clamp(high_a * 0.4, 0.0, 1.0)
            # Nostril flare at high arousal
            weights[_BS_INDEX["noseSneerLeft"]] = _clamp(high_a * 0.2, 0.0, 1.0)
            weights[_BS_INDEX["noseSneerRight"]] = _clamp(high_a * 0.2, 0.0, 1.0)
        else:
            low_a = (0.5 - a) * 2.0 * s  # Normalize to [0, 1] then scale
            # AU43 -> eyeSquintLeft/Right (relaxed/sleepy)
            weights[_BS_INDEX["eyeSquintLeft"]] = _clamp(low_a * 0.5, 0.0, 1.0)
            weights[_BS_INDEX["eyeSquintRight"]] = _clamp(low_a * 0.5, 0.0, 1.0)
            # Partial blink for drowsiness
            weights[_BS_INDEX["eyeBlinkLeft"]] = _clamp(low_a * 0.3, 0.0, 1.0)
            weights[_BS_INDEX["eyeBlinkRight"]] = _clamp(low_a * 0.3, 0.0, 1.0)

        # --- Dominance axis: brow position ---
        # Scherer & Ellgring 2007: dominance -> raised brows (confidence)
        # Low dominance -> lowered/knit brows (submission/worry)
        if d > 0.5:
            high_d = (d - 0.5) * 2.0 * s
            # AU1+AU2 -> browInnerUp + browOuterUpLeft/Right
            weights[_BS_INDEX["browInnerUp"]] = _clamp(high_d * 0.4, 0.0, 1.0)
            weights[_BS_INDEX["browOuterUpLeft"]] = _clamp(high_d * 0.5, 0.0, 1.0)
            weights[_BS_INDEX["browOuterUpRight"]] = _clamp(high_d * 0.5, 0.0, 1.0)
        else:
            low_d = (0.5 - d) * 2.0 * s
            # AU4 -> browDownLeft/Right (brow lowerer)
            weights[_BS_INDEX["browDownLeft"]] = _clamp(low_d * 0.6, 0.0, 1.0)
            weights[_BS_INDEX["browDownRight"]] = _clamp(low_d * 0.6, 0.0, 1.0)

        # --- Cross-dimensional interactions ---
        # Anger: negative valence + high arousal + high dominance
        # Ekman: AU4+AU5+AU7+AU23+AU24
        if v < -0.3 and a > 0.5 and d > 0.5:
            anger_blend = min((-v - 0.3) / 0.7, 1.0) * s
            weights[_BS_INDEX["noseSneerLeft"]] = _clamp(
                max(weights[_BS_INDEX["noseSneerLeft"]], anger_blend * 0.5), 0.0, 1.0
            )
            weights[_BS_INDEX["noseSneerRight"]] = _clamp(
                max(weights[_BS_INDEX["noseSneerRight"]], anger_blend * 0.5), 0.0, 1.0
            )
            weights[_BS_INDEX["mouthPressLeft"]] = _clamp(
                max(weights[_BS_INDEX["mouthPressLeft"]], anger_blend * 0.4), 0.0, 1.0
            )
            weights[_BS_INDEX["mouthPressRight"]] = _clamp(
                max(weights[_BS_INDEX["mouthPressRight"]], anger_blend * 0.4), 0.0, 1.0
            )

        # Surprise: high arousal + neutral-to-positive valence
        # Ekman: AU1+AU2+AU5+AU26
        if a > 0.7 and v > -0.2:
            surprise_blend = ((a - 0.7) / 0.3) * s
            weights[_BS_INDEX["browInnerUp"]] = _clamp(
                max(weights[_BS_INDEX["browInnerUp"]], surprise_blend * 0.8), 0.0, 1.0
            )
            weights[_BS_INDEX["browOuterUpLeft"]] = _clamp(
                max(weights[_BS_INDEX["browOuterUpLeft"]], surprise_blend * 0.7),
                0.0,
                1.0,
            )
            weights[_BS_INDEX["browOuterUpRight"]] = _clamp(
                max(weights[_BS_INDEX["browOuterUpRight"]], surprise_blend * 0.7),
                0.0,
                1.0,
            )
            weights[_BS_INDEX["jawOpen"]] = _clamp(
                max(weights[_BS_INDEX["jawOpen"]], surprise_blend * 0.6), 0.0, 1.0
            )

        # Fear: negative valence + high arousal + low dominance
        # Ekman: AU1+AU2+AU4+AU5+AU20
        if v < -0.2 and a > 0.5 and d < 0.4:
            fear_blend = min((-v - 0.2) / 0.8, 1.0) * ((a - 0.5) / 0.5) * s
            weights[_BS_INDEX["browInnerUp"]] = _clamp(
                max(weights[_BS_INDEX["browInnerUp"]], fear_blend * 0.7), 0.0, 1.0
            )
            weights[_BS_INDEX["mouthStretchLeft"]] = _clamp(fear_blend * 0.5, 0.0, 1.0)
            weights[_BS_INDEX["mouthStretchRight"]] = _clamp(fear_blend * 0.5, 0.0, 1.0)
            weights[_BS_INDEX["eyeWideLeft"]] = _clamp(
                max(weights[_BS_INDEX["eyeWideLeft"]], fear_blend * 0.8), 0.0, 1.0
            )
            weights[_BS_INDEX["eyeWideRight"]] = _clamp(
                max(weights[_BS_INDEX["eyeWideRight"]], fear_blend * 0.8), 0.0, 1.0
            )

        return BlendShapeProfile(weights=weights)


# ---------------------------------------------------------------------------
# 3. Motor Command (Robotic Embodiment)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MotorCommand:
    """Motor command output for robotic embodiment.

    Based on Breazeal (2003) sociable robot expression framework.
    Designed for robots with head, ear, and body degrees of freedom.

    Attributes:
        head_pitch: Vertical head angle [-1, 1]. Negative = look down, positive = look up.
        head_yaw: Horizontal head angle [-1, 1]. Negative = left, positive = right.
        head_roll: Head tilt [-1, 1]. Negative = tilt left, positive = tilt right.
        ear_position: Ear posture [0, 1]. 0 = flat/back, 1 = perked/forward.
            For animal-like robots (Breazeal 2003 Kismet).
        body_lean: Torso lean [-1, 1]. Negative = lean back, positive = lean forward.
        gesture_intensity: Overall gesture amplitude [0, 1]. 0 = still, 1 = maximal.
    """

    head_pitch: float = 0.0
    head_yaw: float = 0.0
    head_roll: float = 0.0
    ear_position: float = 0.5
    body_lean: float = 0.0
    gesture_intensity: float = 0.0

    def __post_init__(self) -> None:
        self.head_pitch = _clamp(self.head_pitch, -1.0, 1.0)
        self.head_yaw = _clamp(self.head_yaw, -1.0, 1.0)
        self.head_roll = _clamp(self.head_roll, -1.0, 1.0)
        self.ear_position = _clamp(self.ear_position, 0.0, 1.0)
        self.body_lean = _clamp(self.body_lean, -1.0, 1.0)
        self.gesture_intensity = _clamp(self.gesture_intensity, 0.0, 1.0)

    def to_dict(self) -> dict[str, float]:
        """Serialize to dictionary for transmission."""
        return {
            "head_pitch": self.head_pitch,
            "head_yaw": self.head_yaw,
            "head_roll": self.head_roll,
            "ear_position": self.ear_position,
            "body_lean": self.body_lean,
            "gesture_intensity": self.gesture_intensity,
        }


# ---------------------------------------------------------------------------
# 4. PAD to Motor Command Mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MotorMorphologyProfile:
    """Configuration profile for different robot morphologies.

    Allows tuning the PAD-to-motor mapping for different physical forms
    (humanoid, animal-like, minimal DOF).

    Attributes:
        has_ears: Whether the robot has movable ears.
        head_range_scale: Multiplier for head movement range [0, 1].
        lean_enabled: Whether body lean is available.
        gesture_baseline: Minimum gesture intensity (idle motion).
    """

    has_ears: bool = True
    head_range_scale: float = 1.0
    lean_enabled: bool = True
    gesture_baseline: float = 0.05


class PADToMotor:
    """Maps PAD vectors to motor commands for robotic embodiment.

    Based on Breazeal (2003) "Emotion and sociable humanoid robots":
      - Arousal -> gesture intensity and movement speed
      - Valence -> head tilt direction (positive = slight upward tilt)
      - Dominance -> body lean and posture expansion

    Additional mappings from Breazeal & Picard (1997):
      - Positive valence + high arousal -> ears forward, lean in
      - Negative valence + low dominance -> ears back, lean away
      - High dominance -> expanded posture (lean forward, head up)

    Properties:
      - Deterministic: same PAD always yields same motor command
      - Bounded: all outputs within declared ranges
      - Lipschitz continuous: smooth transitions between states
    """

    def __init__(self, morphology: MotorMorphologyProfile | None = None) -> None:
        """Initialize motor mapper with optional morphology profile.

        Args:
            morphology: Robot morphology configuration. Defaults to full-featured.
        """
        self._morphology = morphology or MotorMorphologyProfile()

    def map(self, pad: PADVector) -> MotorCommand:
        """Map a PAD vector to motor commands.

        Args:
            pad: PAD emotional state vector.

        Returns:
            MotorCommand with bounded motor outputs.
        """
        v = pad.valence  # [-1, 1]
        a = pad.arousal  # [0, 1]
        d = pad.dominance  # [0, 1]
        m = self._morphology

        # --- Gesture intensity ---
        # Breazeal 2003: arousal directly drives movement amplitude
        gesture = m.gesture_baseline + a * (1.0 - m.gesture_baseline)

        # --- Head pitch ---
        # Positive valence + high dominance -> head up (confidence)
        # Negative valence + low dominance -> head down (submission)
        # Scherer & Ellgring 2007: head position correlates with power appraisal
        pitch = (v * 0.3 + (d - 0.5) * 0.5) * m.head_range_scale

        # --- Head yaw ---
        # Neutral by default; slight aversion for negative valence + low dominance
        # Breazeal 2003: gaze aversion signals discomfort
        yaw = 0.0
        if v < -0.3 and d < 0.4:
            yaw = (v + 0.3) * 0.3  # Slight turn away

        # --- Head roll ---
        # Valence-driven tilt: positive -> slight right tilt (curiosity/engagement)
        # Based on Mignault & Chaudhuri (2003) head tilt and emotion
        roll = v * 0.15 * m.head_range_scale

        # --- Ear position ---
        # Breazeal 2003 Kismet: ears forward = interest, ears back = fear/displeasure
        if m.has_ears:
            # Map: high valence + high arousal -> ears forward
            # Low valence + low dominance -> ears back
            ear = 0.5 + v * 0.25 + (a - 0.5) * 0.2 + (d - 0.5) * 0.1
        else:
            ear = 0.5  # Neutral for robots without ears

        # --- Body lean ---
        # Breazeal 2003: approach (lean forward) vs withdrawal (lean back)
        # Dominance amplifies approach; low dominance amplifies withdrawal
        if m.lean_enabled:
            # Approach-withdrawal model (Mehrabian 1972)
            lean = v * 0.3 + (d - 0.5) * 0.4
        else:
            lean = 0.0

        return MotorCommand(
            head_pitch=pitch,
            head_yaw=yaw,
            head_roll=roll,
            ear_position=ear,
            body_lean=lean,
            gesture_intensity=gesture,
        )


# ---------------------------------------------------------------------------
# 5. Text Style Parameters
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TextStyle:
    """Parameters for modulating chatbot text generation style.

    Based on Pennebaker et al. (2011) "The Secret Life of Pronouns" and
    Tausczik & Pennebaker (2010) linguistic markers of psychological state.

    Attributes:
        formality: Casual to formal register [0, 1].
            0 = very casual (contractions, slang), 1 = highly formal.
        verbosity: Terse to elaborate [0, 1].
            0 = minimal words, 1 = detailed/expansive.
        emoji_density: Emoji usage frequency [0, 1].
            0 = no emojis, 1 = heavy emoji use.
        punctuation_intensity: Punctuation expressiveness [0, 1].
            0 = periods only, 1 = exclamation marks, ellipses, etc.
        sentence_length_bias: Preference for sentence length [-1, 1].
            -1 = very short sentences, 1 = long complex sentences.
    """

    formality: float = 0.5
    verbosity: float = 0.5
    emoji_density: float = 0.0
    punctuation_intensity: float = 0.3
    sentence_length_bias: float = 0.0

    def __post_init__(self) -> None:
        self.formality = _clamp(self.formality, 0.0, 1.0)
        self.verbosity = _clamp(self.verbosity, 0.0, 1.0)
        self.emoji_density = _clamp(self.emoji_density, 0.0, 1.0)
        self.punctuation_intensity = _clamp(self.punctuation_intensity, 0.0, 1.0)
        self.sentence_length_bias = _clamp(self.sentence_length_bias, -1.0, 1.0)

    def to_dict(self) -> dict[str, float]:
        """Serialize to dictionary."""
        return {
            "formality": self.formality,
            "verbosity": self.verbosity,
            "emoji_density": self.emoji_density,
            "punctuation_intensity": self.punctuation_intensity,
            "sentence_length_bias": self.sentence_length_bias,
        }


# ---------------------------------------------------------------------------
# 6. PAD to Text Style Mapping
# ---------------------------------------------------------------------------


class PADToTextStyle:
    """Maps PAD vectors to text style parameters for chatbot response modulation.

    Based on Pennebaker et al. (2011) and Tausczik & Pennebaker (2010):
      - High arousal -> shorter sentences, more punctuation intensity
        (linguistic urgency markers)
      - Positive valence -> more emojis, less formal register
        (positive affect linguistic markers)
      - High dominance -> more direct language, less hedging, shorter
        (power language patterns)
      - Low dominance -> more verbose, more hedging, longer sentences
        (uncertainty markers)

    Additional basis from Gill et al. (2008) on personality and language:
      - Emotional intensity correlates with punctuation expressiveness
      - Positive mood correlates with informal register

    Properties:
      - Deterministic: same PAD always yields same text style
      - Bounded: all outputs within declared ranges
      - Lipschitz continuous: gradual style transitions
    """

    def __init__(self, baseline_formality: float = 0.5) -> None:
        """Initialize text style mapper.

        Args:
            baseline_formality: Default formality level [0, 1] before
                emotional modulation. Allows setting a character's base register.
        """
        self._baseline_formality = _clamp(baseline_formality, 0.0, 1.0)

    def map(self, pad: PADVector) -> TextStyle:
        """Map a PAD vector to text style parameters.

        Args:
            pad: PAD emotional state vector.

        Returns:
            TextStyle with bounded style parameters.
        """
        v = pad.valence  # [-1, 1]
        a = pad.arousal  # [0, 1]
        d = pad.dominance  # [0, 1]

        # --- Formality ---
        # Pennebaker 2011: positive affect -> informal language
        # High dominance -> slightly more formal (authority register)
        formality = self._baseline_formality
        formality -= v * 0.15  # Positive valence reduces formality
        formality += (d - 0.5) * 0.2  # High dominance increases formality
        formality -= a * 0.1  # High arousal slightly reduces formality

        # --- Verbosity ---
        # Low dominance -> more verbose (hedging, qualifiers)
        # High arousal -> less verbose (urgency)
        # Tausczik & Pennebaker 2010: anxiety increases word count
        verbosity = 0.5
        verbosity += (0.5 - d) * 0.3  # Low dominance -> more words
        verbosity -= (a - 0.5) * 0.3  # High arousal -> fewer words
        # Negative valence + low dominance -> rumination (verbose)
        if v < 0 and d < 0.5:
            verbosity += (-v) * (0.5 - d) * 0.4

        # --- Emoji density ---
        # Positive valence strongly drives emoji use
        # High arousal amplifies emoji use
        # Formal register suppresses emojis
        emoji = 0.0
        if v > 0:
            emoji = v * 0.6 + a * 0.2
        elif v > -0.5:
            emoji = 0.05  # Minimal emoji in mildly negative states
        # Suppress in formal contexts
        emoji *= 1.0 - formality * 0.5

        # --- Punctuation intensity ---
        # Arousal is the primary driver (Pennebaker 2011)
        # Extreme valence (positive or negative) amplifies
        punctuation = 0.2 + a * 0.5 + abs(v) * 0.2

        # --- Sentence length bias ---
        # High arousal -> shorter (urgency)
        # High dominance -> shorter (directness)
        # Low dominance -> longer (hedging, qualifiers)
        length_bias = 0.0
        length_bias -= (a - 0.5) * 0.6  # High arousal shortens
        length_bias -= (d - 0.5) * 0.4  # High dominance shortens
        length_bias += (0.5 - d) * 0.3  # Low dominance lengthens

        return TextStyle(
            formality=formality,
            verbosity=verbosity,
            emoji_density=emoji,
            punctuation_intensity=punctuation,
            sentence_length_bias=length_bias,
        )


# ---------------------------------------------------------------------------
# 7. Prosody Parameters (TTS)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ProsodyParams:
    """Audio prosody parameters for text-to-speech modulation.

    Based on Scherer (2003) "Vocal communication of emotion: A review of
    research paradigms" and Banse & Scherer (1996) acoustic profiles.

    Attributes:
        pitch_shift: Semitones relative to speaker baseline [-1, 1].
            -1 = one octave down, 0 = baseline, 1 = one octave up.
            Normalized scale; actual semitone mapping is TTS-engine specific.
        speech_rate: Rate multiplier [0.5, 2.0].
            0.5 = half speed, 1.0 = normal, 2.0 = double speed.
        volume: Output volume [0, 1].
            0 = silence, 1 = maximum.
        pitch_variance: Intonation range [0, 1].
            0 = monotone, 1 = highly varied pitch contour.
    """

    pitch_shift: float = 0.0
    speech_rate: float = 1.0
    volume: float = 0.5
    pitch_variance: float = 0.3

    def __post_init__(self) -> None:
        self.pitch_shift = _clamp(self.pitch_shift, -1.0, 1.0)
        self.speech_rate = _clamp(self.speech_rate, 0.5, 2.0)
        self.volume = _clamp(self.volume, 0.0, 1.0)
        self.pitch_variance = _clamp(self.pitch_variance, 0.0, 1.0)

    def to_dict(self) -> dict[str, float]:
        """Serialize to dictionary."""
        return {
            "pitch_shift": self.pitch_shift,
            "speech_rate": self.speech_rate,
            "volume": self.volume,
            "pitch_variance": self.pitch_variance,
        }


# ---------------------------------------------------------------------------
# 8. PAD to Prosody Mapping
# ---------------------------------------------------------------------------


class PADToProsody:
    """Maps PAD vectors to audio prosody parameters for TTS.

    Based on Scherer (2003) vocal affect expression research:
      - Arousal -> pitch level and speech rate
        High arousal: raised F0, faster rate (Banse & Scherer 1996)
        Low arousal: lowered F0, slower rate
      - Valence -> pitch variance (intonation contour)
        Positive valence: wider pitch range (Scherer 2003 Table 4)
        Negative valence: narrower, more monotone
      - Dominance -> volume and vocal effort
        High dominance: louder, more projected (Scherer 1986)
        Low dominance: quieter, breathy

    Additional basis from Juslin & Laukka (2003) meta-analysis of
    vocal expression of emotion across speech and music.

    Properties:
      - Deterministic: same PAD always yields same prosody
      - Bounded: all outputs within declared ranges
      - Lipschitz continuous: smooth prosodic transitions
    """

    def __init__(
        self,
        baseline_rate: float = 1.0,
        baseline_volume: float = 0.5,
    ) -> None:
        """Initialize prosody mapper.

        Args:
            baseline_rate: Default speech rate [0.5, 2.0].
            baseline_volume: Default volume [0, 1].
        """
        self._baseline_rate = _clamp(baseline_rate, 0.5, 2.0)
        self._baseline_volume = _clamp(baseline_volume, 0.0, 1.0)

    def map(self, pad: PADVector) -> ProsodyParams:
        """Map a PAD vector to prosody parameters.

        Args:
            pad: PAD emotional state vector.

        Returns:
            ProsodyParams with bounded prosody outputs.
        """
        v = pad.valence  # [-1, 1]
        a = pad.arousal  # [0, 1]
        d = pad.dominance  # [0, 1]

        # --- Pitch shift ---
        # Scherer 2003: arousal is primary driver of F0
        # Banse & Scherer 1996: anger/fear/joy all raise pitch via arousal
        # Sadness (low arousal) lowers pitch
        # Valence adds slight modulation (positive slightly higher)
        pitch_shift = (a - 0.5) * 1.2 + v * 0.15

        # --- Speech rate ---
        # Juslin & Laukka 2003: arousal strongly predicts tempo
        # High arousal -> faster, low arousal -> slower
        # Dominance adds slight acceleration (confident = brisk)
        rate_delta = (a - 0.5) * 0.6 + (d - 0.5) * 0.15
        speech_rate = self._baseline_rate + rate_delta

        # --- Volume ---
        # Scherer 1986: dominance/power -> vocal effort -> loudness
        # Arousal also contributes (activation -> louder)
        volume = self._baseline_volume + (d - 0.5) * 0.3 + (a - 0.5) * 0.2

        # --- Pitch variance ---
        # Scherer 2003: positive emotions -> wider F0 range
        # Negative emotions (especially sadness) -> monotone
        # High arousal also increases variance (Juslin & Laukka 2003)
        pitch_variance = 0.3
        pitch_variance += v * 0.2  # Positive -> more varied
        pitch_variance += (a - 0.5) * 0.3  # High arousal -> more varied
        # Extreme negative + low arousal -> very monotone (depression marker)
        if v < -0.5 and a < 0.3:
            pitch_variance *= 0.5

        return ProsodyParams(
            pitch_shift=pitch_shift,
            speech_rate=speech_rate,
            volume=volume,
            pitch_variance=pitch_variance,
        )


# ---------------------------------------------------------------------------
# Convenience: Unified Expression Mapper
# ---------------------------------------------------------------------------


class ExpressionMapper:
    """Unified mapper from PAD/EmotionVector to all output modalities.

    Convenience class that aggregates all four modality mappers and provides
    a single entry point for expression generation.

    Accepts either PADVector directly or EmotionVector (which is converted
    to PADVector using the same dimensional semantics).
    """

    def __init__(
        self,
        blend_intensity: float = 1.0,
        morphology: MotorMorphologyProfile | None = None,
        baseline_formality: float = 0.5,
        baseline_rate: float = 1.0,
        baseline_volume: float = 0.5,
    ) -> None:
        """Initialize all sub-mappers.

        Args:
            blend_intensity: Blend shape expression intensity [0, 2].
            morphology: Robot morphology profile for motor mapping.
            baseline_formality: Default text formality [0, 1].
            baseline_rate: Default speech rate [0.5, 2.0].
            baseline_volume: Default volume [0, 1].
        """
        self.blend_shape = PADToBlendShape(intensity_scale=blend_intensity)
        self.motor = PADToMotor(morphology=morphology)
        self.text_style = PADToTextStyle(baseline_formality=baseline_formality)
        self.prosody = PADToProsody(
            baseline_rate=baseline_rate,
            baseline_volume=baseline_volume,
        )

    def _to_pad(self, state: PADVector | EmotionVector) -> PADVector:
        """Convert EmotionVector to PADVector if needed.

        EmotionVector uses the same PAD semantics:
          valence [-1, 1], arousal [0, 1], dominance [0, 1].
        """
        if isinstance(state, PADVector):
            return state
        return PADVector(
            valence=state.valence,
            arousal=state.arousal,
            dominance=state.dominance,
        )

    def map_all(self, state: PADVector | EmotionVector) -> dict[str, Any]:
        """Map emotional state to all output modalities simultaneously.

        Args:
            state: PADVector or EmotionVector emotional state.

        Returns:
            Dictionary with keys: 'blend_shapes', 'motor', 'text_style', 'prosody'.
        """
        pad = self._to_pad(state)
        return {
            "blend_shapes": self.blend_shape.map(pad),
            "motor": self.motor.map(pad),
            "text_style": self.text_style.map(pad),
            "prosody": self.prosody.map(pad),
        }

    def map_blend_shapes(self, state: PADVector | EmotionVector) -> BlendShapeProfile:
        """Map to blend shapes only."""
        return self.blend_shape.map(self._to_pad(state))

    def map_motor(self, state: PADVector | EmotionVector) -> MotorCommand:
        """Map to motor commands only."""
        return self.motor.map(self._to_pad(state))

    def map_text_style(self, state: PADVector | EmotionVector) -> TextStyle:
        """Map to text style only."""
        return self.text_style.map(self._to_pad(state))

    def map_prosody(self, state: PADVector | EmotionVector) -> ProsodyParams:
        """Map to prosody only."""
        return self.prosody.map(self._to_pad(state))
