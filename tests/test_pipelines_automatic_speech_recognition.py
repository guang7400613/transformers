# Copyright 2021 The HuggingFace Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

import numpy as np
import pytest
from datasets import load_dataset

from transformers import (
    MODEL_FOR_CTC_MAPPING,
    MODEL_FOR_SPEECH_SEQ_2_SEQ_MAPPING,
    AutoFeatureExtractor,
    AutoTokenizer,
    Speech2TextForConditionalGeneration,
    Wav2Vec2ForCTC,
)
from transformers.pipelines import AutomaticSpeechRecognitionPipeline, pipeline
from transformers.pipelines.automatic_speech_recognition import apply_stride, chunk_iter
from transformers.testing_utils import (
    is_pipeline_test,
    is_torch_available,
    nested_simplify,
    require_tf,
    require_torch,
    require_torchaudio,
    slow,
)

from .test_pipelines_common import ANY, PipelineTestCaseMeta


if is_torch_available():
    import torch


# We can't use this mixin because it assumes TF support.
# from .test_pipelines_common import CustomInputPipelineCommonMixin


@is_pipeline_test
class AutomaticSpeechRecognitionPipelineTests(unittest.TestCase, metaclass=PipelineTestCaseMeta):
    model_mapping = {
        k: v
        for k, v in (list(MODEL_FOR_SPEECH_SEQ_2_SEQ_MAPPING.items()) if MODEL_FOR_SPEECH_SEQ_2_SEQ_MAPPING else [])
        + (MODEL_FOR_CTC_MAPPING.items() if MODEL_FOR_CTC_MAPPING else [])
    }

    def get_test_pipeline(self, model, tokenizer, feature_extractor):
        if tokenizer is None:
            # Side effect of no Fast Tokenizer class for these model, so skipping
            # But the slow tokenizer test should still run as they're quite small
            self.skipTest("No tokenizer available")
            return
            # return None, None

        speech_recognizer = AutomaticSpeechRecognitionPipeline(
            model=model, tokenizer=tokenizer, feature_extractor=feature_extractor
        )

        # test with a raw waveform
        audio = np.zeros((34000,))
        audio2 = np.zeros((14000,))
        return speech_recognizer, [audio, audio2]

    def run_pipeline_test(self, speech_recognizer, examples):
        audio = np.zeros((34000,))
        outputs = speech_recognizer(audio)
        self.assertEqual(outputs, {"text": ANY(str)})

    @require_torch
    @slow
    def test_pt_defaults(self):
        pipeline("automatic-speech-recognition", framework="pt")

    @require_torch
    def test_small_model_pt(self):

        speech_recognizer = pipeline(
            task="automatic-speech-recognition",
            model="facebook/s2t-small-mustc-en-fr-st",
            tokenizer="facebook/s2t-small-mustc-en-fr-st",
            framework="pt",
        )
        waveform = np.tile(np.arange(1000, dtype=np.float32), 34)
        output = speech_recognizer(waveform)
        self.assertEqual(output, {"text": "(Applaudissements)"})

    @require_tf
    def test_small_model_tf(self):
        self.skipTest("Tensorflow not supported yet.")

    @require_torch
    def test_torch_small_no_tokenizer_files(self):
        # test that model without tokenizer file cannot be loaded
        with pytest.raises(OSError):
            pipeline(
                task="automatic-speech-recognition",
                model="patrickvonplaten/tiny-wav2vec2-no-tokenizer",
                framework="pt",
            )

    @require_torch
    @slow
    def test_torch_large(self):

        speech_recognizer = pipeline(
            task="automatic-speech-recognition",
            model="facebook/wav2vec2-base-960h",
            tokenizer="facebook/wav2vec2-base-960h",
            framework="pt",
        )
        waveform = np.tile(np.arange(1000, dtype=np.float32), 34)
        output = speech_recognizer(waveform)
        self.assertEqual(output, {"text": ""})

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        filename = ds[40]["file"]
        output = speech_recognizer(filename)
        self.assertEqual(output, {"text": "A MAN SAID TO THE UNIVERSE SIR I EXIST"})

    @require_torch
    @slow
    def test_torch_speech_encoder_decoder(self):
        speech_recognizer = pipeline(
            task="automatic-speech-recognition",
            model="facebook/s2t-wav2vec2-large-en-de",
            feature_extractor="facebook/s2t-wav2vec2-large-en-de",
            framework="pt",
        )

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        filename = ds[40]["file"]
        output = speech_recognizer(filename)
        self.assertEqual(output, {"text": 'Ein Mann sagte zum Universum : " Sir, ich existiert! "'})

    @slow
    @require_torch
    def test_simple_wav2vec2(self):

        model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
        tokenizer = AutoTokenizer.from_pretrained("facebook/wav2vec2-base-960h")
        feature_extractor = AutoFeatureExtractor.from_pretrained("facebook/wav2vec2-base-960h")

        asr = AutomaticSpeechRecognitionPipeline(model=model, tokenizer=tokenizer, feature_extractor=feature_extractor)

        waveform = np.tile(np.arange(1000, dtype=np.float32), 34)
        output = asr(waveform)
        self.assertEqual(output, {"text": ""})

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        filename = ds[40]["file"]
        output = asr(filename)
        self.assertEqual(output, {"text": "A MAN SAID TO THE UNIVERSE SIR I EXIST"})

        filename = ds[40]["file"]
        with open(filename, "rb") as f:
            data = f.read()
        output = asr(data)
        self.assertEqual(output, {"text": "A MAN SAID TO THE UNIVERSE SIR I EXIST"})

    @slow
    @require_torch
    @require_torchaudio
    def test_simple_s2t(self):

        model = Speech2TextForConditionalGeneration.from_pretrained("facebook/s2t-small-mustc-en-it-st")
        tokenizer = AutoTokenizer.from_pretrained("facebook/s2t-small-mustc-en-it-st")
        feature_extractor = AutoFeatureExtractor.from_pretrained("facebook/s2t-small-mustc-en-it-st")

        asr = AutomaticSpeechRecognitionPipeline(model=model, tokenizer=tokenizer, feature_extractor=feature_extractor)

        waveform = np.tile(np.arange(1000, dtype=np.float32), 34)

        output = asr(waveform)
        self.assertEqual(output, {"text": "(Applausi)"})

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        filename = ds[40]["file"]
        output = asr(filename)
        self.assertEqual(output, {"text": "Un uomo disse all'universo: \"Signore, io esisto."})

        filename = ds[40]["file"]
        with open(filename, "rb") as f:
            data = f.read()
        output = asr(data)
        self.assertEqual(output, {"text": "Un uomo disse all'universo: \"Signore, io esisto."})

    @slow
    @require_torch
    @require_torchaudio
    def test_xls_r_to_en(self):
        speech_recognizer = pipeline(
            task="automatic-speech-recognition",
            model="facebook/wav2vec2-xls-r-1b-21-to-en",
            feature_extractor="facebook/wav2vec2-xls-r-1b-21-to-en",
            framework="pt",
        )

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        filename = ds[40]["file"]
        output = speech_recognizer(filename)
        self.assertEqual(output, {"text": "A man said to the universe: “Sir, I exist."})

    @slow
    @require_torch
    @require_torchaudio
    def test_xls_r_from_en(self):
        speech_recognizer = pipeline(
            task="automatic-speech-recognition",
            model="facebook/wav2vec2-xls-r-1b-en-to-15",
            feature_extractor="facebook/wav2vec2-xls-r-1b-en-to-15",
            framework="pt",
        )

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        filename = ds[40]["file"]
        output = speech_recognizer(filename)
        self.assertEqual(output, {"text": "Ein Mann sagte zu dem Universum, Sir, ich bin da."})

    @slow
    @require_torch
    @require_torchaudio
    def test_speech_to_text_leveraged(self):
        speech_recognizer = pipeline(
            task="automatic-speech-recognition",
            model="patrickvonplaten/wav2vec2-2-bart-base",
            feature_extractor="patrickvonplaten/wav2vec2-2-bart-base",
            tokenizer=AutoTokenizer.from_pretrained("patrickvonplaten/wav2vec2-2-bart-base"),
            framework="pt",
        )

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        filename = ds[40]["file"]
        output = speech_recognizer(filename)
        self.assertEqual(output, {"text": "a man said to the universe sir i exist"})

    @require_torch
    @slow
    def test_chunking(self):
        model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
        tokenizer = AutoTokenizer.from_pretrained("facebook/wav2vec2-base-960h")
        feature_extractor = AutoFeatureExtractor.from_pretrained("facebook/wav2vec2-base-960h")
        speech_recognizer = pipeline(
            task="automatic-speech-recognition",
            model=model,
            tokenizer=tokenizer,
            feature_extractor=feature_extractor,
            framework="pt",
            chunk_length_s=10.0,
        )

        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation").sort("id")
        audio = ds[40]["audio"]["array"]

        n_repeats = 10
        audio = np.tile(audio, n_repeats)
        output = speech_recognizer([audio], batch_size=2)
        expected_text = "A MAN SAID TO THE UNIVERSE SIR I EXIST " * n_repeats
        expected = [{"text": expected_text.strip()}]
        self.assertEqual(output, expected)

    @require_torch
    def test_chunk_iterator(self):
        feature_extractor = AutoFeatureExtractor.from_pretrained("facebook/wav2vec2-base-960h")
        inputs = torch.arange(100).long()

        outs = list(chunk_iter(inputs, feature_extractor, 100, 0, 0))
        self.assertEqual(len(outs), 1)
        self.assertEqual([o["stride"] for o in outs], [(100, 0, 0)])
        self.assertEqual([o["input_values"].shape for o in outs], [(1, 100)])
        self.assertEqual([o["is_last"] for o in outs], [True])

        # two chunks no stride
        outs = list(chunk_iter(inputs, feature_extractor, 50, 0, 0))
        self.assertEqual(len(outs), 2)
        self.assertEqual([o["stride"] for o in outs], [(50, 0, 0), (50, 0, 0)])
        self.assertEqual([o["input_values"].shape for o in outs], [(1, 50), (1, 50)])
        self.assertEqual([o["is_last"] for o in outs], [False, True])

        # two chunks incomplete last
        outs = list(chunk_iter(inputs, feature_extractor, 80, 0, 0))
        self.assertEqual(len(outs), 2)
        self.assertEqual([o["stride"] for o in outs], [(80, 0, 0), (20, 0, 0)])
        self.assertEqual([o["input_values"].shape for o in outs], [(1, 80), (1, 20)])
        self.assertEqual([o["is_last"] for o in outs], [False, True])

    @require_torch
    def test_chunk_iterator_stride(self):
        feature_extractor = AutoFeatureExtractor.from_pretrained("facebook/wav2vec2-base-960h")
        inputs = torch.arange(100).long()
        input_values = feature_extractor(inputs, sampling_rate=feature_extractor.sampling_rate, return_tensors="pt")[
            "input_values"
        ]

        outs = list(chunk_iter(inputs, feature_extractor, 100, 20, 10))
        self.assertEqual(len(outs), 2)
        self.assertEqual([o["stride"] for o in outs], [(100, 0, 10), (30, 20, 0)])
        self.assertEqual([o["input_values"].shape for o in outs], [(1, 100), (1, 30)])
        self.assertEqual([o["is_last"] for o in outs], [False, True])

        outs = list(chunk_iter(inputs, feature_extractor, 80, 20, 10))
        self.assertEqual(len(outs), 2)
        self.assertEqual([o["stride"] for o in outs], [(80, 0, 10), (50, 20, 0)])
        self.assertEqual([o["input_values"].shape for o in outs], [(1, 80), (1, 50)])
        self.assertEqual([o["is_last"] for o in outs], [False, True])

        outs = list(chunk_iter(inputs, feature_extractor, 90, 20, 0))
        self.assertEqual(len(outs), 2)
        self.assertEqual([o["stride"] for o in outs], [(90, 0, 0), (30, 20, 0)])
        self.assertEqual([o["input_values"].shape for o in outs], [(1, 90), (1, 30)])

        inputs = torch.LongTensor([i % 2 for i in range(100)])
        input_values = feature_extractor(inputs, sampling_rate=feature_extractor.sampling_rate, return_tensors="pt")[
            "input_values"
        ]
        outs = list(chunk_iter(inputs, feature_extractor, 30, 5, 5))
        self.assertEqual(len(outs), 5)
        self.assertEqual([o["stride"] for o in outs], [(30, 0, 5), (30, 5, 5), (30, 5, 5), (30, 5, 5), (20, 5, 0)])
        self.assertEqual([o["input_values"].shape for o in outs], [(1, 30), (1, 30), (1, 30), (1, 30), (1, 20)])
        self.assertEqual([o["is_last"] for o in outs], [False, False, False, False, True])
        # (0, 25)
        self.assertEqual(nested_simplify(input_values[:, :30]), nested_simplify(outs[0]["input_values"]))
        # (25, 45)
        self.assertEqual(nested_simplify(input_values[:, 20:50]), nested_simplify(outs[1]["input_values"]))
        # (45, 65)
        self.assertEqual(nested_simplify(input_values[:, 40:70]), nested_simplify(outs[2]["input_values"]))
        # (65, 85)
        self.assertEqual(nested_simplify(input_values[:, 60:90]), nested_simplify(outs[3]["input_values"]))
        # (85, 100)
        self.assertEqual(nested_simplify(input_values[:, 80:100]), nested_simplify(outs[4]["input_values"]))


@require_torch
class ApplyStrideTest(unittest.TestCase):
    def test_apply_stride(self):
        tokens = torch.arange(10).long().reshape((2, 5))

        # No stride
        apply_stride(tokens, [(100, 0, 0), (100, 0, 0)])

        expected = torch.arange(10).long().reshape((2, 5))
        self.assertEqual(expected.tolist(), tokens.tolist())

    def test_apply_stride_real_stride(self):
        # Stride aligned
        tokens = torch.arange(10).long().reshape((2, 5))
        apply_stride(tokens, [(100, 20, 0), (100, 0, 20)])
        self.assertEqual([[1, 1, 2, 3, 4], [5, 6, 7, 8, 8]], tokens.tolist())

        # Stride rounded
        tokens = torch.arange(10).long().reshape((2, 5))
        apply_stride(tokens, [(100, 15, 0), (100, 0, 15)])
        self.assertEqual([[1, 1, 2, 3, 4], [5, 6, 7, 8, 8]], tokens.tolist())

        # No stride rounded
        tokens = torch.arange(10).long().reshape((2, 5))
        apply_stride(tokens, [(100, 5, 0), (100, 0, 5)])
        self.assertEqual([[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]], tokens.tolist())

    def test_apply_stride_with_padding(self):
        # Stride aligned
        tokens = torch.arange(10).long().reshape((2, 5))
        apply_stride(tokens, [(100, 20, 0), (60, 0, 20)])
        self.assertEqual([[1, 1, 2, 3, 4], [5, 6, 6, 6, 6]], tokens.tolist())
