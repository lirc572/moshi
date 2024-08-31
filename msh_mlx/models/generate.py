# Copyright (c) Kyutai, all rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass
from typing import List, Optional, Tuple

import mlx.core as mx
import mlx.nn as nn

from ..models import Lm
from ..utils import sampling

class LmGen:
    def __init__(
        self,
        model: Lm,
        max_steps: int,
        text_sampler: sampling.Sampler,
        audio_sampler: sampling.Sampler,
        check: bool = False,
    ):
        self.model: Lm = model
        self.text_sampler = text_sampler
        self.audio_sampler = audio_sampler
        self.max_steps = max_steps
        self.check = check
        self.num_codebooks = 1 + model.cfg.audio_codebooks
        self.gen_sequence = mx.full(
            shape=(1, self.num_codebooks, max_steps),
            vals=self.ungenerated_token,
            dtype=mx.int32,
        )
        self.step_idx = 0
        self.cache = None
        self.audio_padding_token = self.model.cfg.audio_padding_token
        self.audio_delays = self.model.cfg.audio_delays
        self.main_codebooks = self.model.cfg.depformer.num_slices


    @property
    def zero_token(self) -> int:
        """Special value in the input tokens, indicating that no sampling should
        happen for that value, and no input should be given to the model."""
        return -1

    @property
    def ungenerated_token(self) -> int:
        """Special value that can be provided in the prompt to indicate that this specific
        value should be predicted and sampled. This allows for partial teacher forcing, by generating
        one modality, with the other one fixed.
        """
        return -2

    def step(self, other_audio_tokens: mx.array):
        if self.step_idx >= self.max_steps:
            raise ValueError(f"reached max-steps {self.max_steps}")

        if self.step_idx == 0:
            text_tokens = mx.array([[32000]])
        else:
            text_tokens = self.gen_sequence[:, 0, self.step_idx - 1][None]
        self.gen_sequence[:, 1 + self.main_codebooks:, self.step_idx] = other_audio_tokens
        audio_tokens = []
        for cb_idx, delay in enumerate(self.audio_delays):
            gen_idx = self.step_idx - 1 - delay
            if gen_idx >= 0:
                audio_token = self.gen_sequence[:, cb_idx + 1, gen_idx][None]
            else:
                audio_token = mx.array([[self.audio_padding_token]])
            if (audio_token == self.ungenerated_token).any():
                raise ValueError(f"ungenerated value in audio tokens cb: {cb_idx} step: {self.step_idx}")
            assert audio_token.shape == (1, 1), "invalid audio-tokens shape"
            audio_tokens.append(audio_token)
        if (text_tokens == self.ungenerated_token).any():
            raise ValueError(f"ungenerated value in text tokens {self.step_idx}")
        assert text_tokens.shape == (1, 1), "invalid text-tokens shape"
        text_tokens, audio_tokens, cache = self.model.sample(
            text_tokens,
            audio_tokens,
            self.text_sampler,
            self.audio_sampler,
            self.cache,
        )
        assert text_tokens.shape == (1, ), "invalid output text-token shape"
        assert audio_tokens.shape == (8, ), "invalid output audio-token shape"

        self.gen_sequence[:, 0, self.step_idx] = text_tokens
        for cb_idx, delay in enumerate(self.audio_delays[:self.main_codebooks]):
            gen_idx = self.step_idx - delay
            if gen_idx >= 0:
                self.gen_sequence[:, cb_idx + 1, gen_idx] = audio_tokens[cb_idx]
        self.cache = cache
        self.step_idx += 1