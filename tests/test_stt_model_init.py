from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import call, patch

from core import stt


class SttModelInitializationTests(unittest.TestCase):
    def setUp(self):
        self.previous_model = stt.model
        stt.model = None

        self.preload_patcher = patch.object(
            stt,
            "_preload_gpu_runtime_dlls",
        )
        self.preload_gpu_runtime = self.preload_patcher.start()

    def tearDown(self):
        self.preload_patcher.stop()
        stt.model = self.previous_model

    def test_prefers_gpu_distil_small_model(self):
        gpu_model = object()
        calls = []

        def fake_whisper_model(model_name, **options):
            calls.append((model_name, options))
            return gpu_model

        with patch.object(
            stt,
            "WhisperModel",
            side_effect=fake_whisper_model,
        ):
            stt.init_model()

        self.assertIs(stt.model, gpu_model)
        self.preload_gpu_runtime.assert_called_once_with()
        self.assertEqual(
            calls,
            [
                (
                    stt.STT_PRIMARY_MODEL,
                    {
                        "device": stt.STT_GPU_DEVICE,
                        "compute_type": stt.STT_GPU_COMPUTE_TYPE,
                    },
                ),
            ],
        )

    def test_falls_back_to_cpu_distil_small_when_gpu_fails(self):
        cpu_model = object()
        calls = []

        def fake_whisper_model(model_name, **options):
            calls.append((model_name, options))

            if options["device"] == stt.STT_GPU_DEVICE:
                raise RuntimeError("CUDA unavailable")

            return cpu_model

        with patch.object(
            stt,
            "WhisperModel",
            side_effect=fake_whisper_model,
        ):
            stt.init_model()

        self.assertIs(stt.model, cpu_model)
        self.assertEqual(
            calls,
            [
                (
                    stt.STT_PRIMARY_MODEL,
                    {
                        "device": stt.STT_GPU_DEVICE,
                        "compute_type": stt.STT_GPU_COMPUTE_TYPE,
                    },
                ),
                (
                    stt.STT_PRIMARY_MODEL,
                    {
                        "device": stt.STT_CPU_DEVICE,
                        "compute_type": stt.STT_CPU_COMPUTE_TYPE,
                        "cpu_threads": stt.STT_CPU_THREADS,
                    },
                ),
            ],
        )

    def test_falls_back_to_tiny_cpu_model_when_distil_small_fails(self):
        fallback_model = object()
        calls = []

        def fake_whisper_model(model_name, **options):
            calls.append((model_name, options))

            if model_name == stt.STT_PRIMARY_MODEL:
                raise RuntimeError("distil-small unavailable")

            return fallback_model

        with patch.object(
            stt,
            "WhisperModel",
            side_effect=fake_whisper_model,
        ):
            stt.init_model()

        self.assertIs(stt.model, fallback_model)
        self.assertEqual(
            calls,
            [
                (
                    stt.STT_PRIMARY_MODEL,
                    {
                        "device": stt.STT_GPU_DEVICE,
                        "compute_type": stt.STT_GPU_COMPUTE_TYPE,
                    },
                ),
                (
                    stt.STT_PRIMARY_MODEL,
                    {
                        "device": stt.STT_CPU_DEVICE,
                        "compute_type": stt.STT_CPU_COMPUTE_TYPE,
                        "cpu_threads": stt.STT_CPU_THREADS,
                    },
                ),
                (
                    stt.STT_FALLBACK_MODEL,
                    {
                        "device": stt.STT_CPU_DEVICE,
                        "compute_type": stt.STT_CPU_COMPUTE_TYPE,
                        "cpu_threads": stt.STT_CPU_THREADS,
                    },
                ),
            ],
        )

    def test_keeps_existing_model_without_reinitializing(self):
        existing_model = object()
        stt.model = existing_model

        with patch.object(stt, "WhisperModel") as whisper_model:
            stt.init_model()

        self.assertIs(stt.model, existing_model)
        whisper_model.assert_not_called()
        self.preload_gpu_runtime.assert_not_called()

    def test_leaves_model_unavailable_when_all_attempts_fail(self):
        with patch.object(
            stt,
            "WhisperModel",
            side_effect=RuntimeError("all backends failed"),
        ) as whisper_model:
            stt.init_model()

        self.assertIsNone(stt.model)
        self.assertEqual(whisper_model.call_count, 3)


class GpuRuntimePreloadTests(unittest.TestCase):
    def setUp(self):
        self.previous_preloaded = stt._gpu_runtime_preloaded
        self.previous_directory_handles = (
            stt._gpu_runtime_dll_directory_handles
        )
        self.previous_dll_handles = stt._gpu_runtime_dll_handles

        stt._gpu_runtime_preloaded = False
        stt._gpu_runtime_dll_directory_handles = []
        stt._gpu_runtime_dll_handles = []

    def tearDown(self):
        stt._gpu_runtime_preloaded = self.previous_preloaded
        stt._gpu_runtime_dll_directory_handles = (
            self.previous_directory_handles
        )
        stt._gpu_runtime_dll_handles = self.previous_dll_handles

    def test_skips_preload_outside_windows(self):
        with patch.object(stt.os, "name", "posix"), patch.object(
            stt,
            "_find_gpu_runtime_dll_path",
        ) as find_dll, patch.object(
            stt.ctypes,
            "WinDLL",
            create=True,
        ) as win_dll:
            stt._preload_gpu_runtime_dlls()

        find_dll.assert_not_called()
        win_dll.assert_not_called()
        self.assertFalse(stt._gpu_runtime_preloaded)

    def test_preloads_runtime_dlls_from_absolute_paths(self):
        cuda_directory = Path(r"C:\CUDA\bin")
        cudnn_directory = Path(r"C:\cuDNN\bin")

        dll_paths = [
            cuda_directory / "cublasLt64_12.dll",
            cuda_directory / "cublas64_12.dll",
            cudnn_directory / "cudnn64_9.dll",
        ]

        cuda_directory_handle = object()
        cudnn_directory_handle = object()
        cublas_lt_handle = object()
        cublas_handle = object()
        cudnn_handle = object()

        with patch.object(stt.os, "name", "nt"), patch.object(
            stt,
            "_find_gpu_runtime_dll_path",
            side_effect=dll_paths,
        ) as find_dll, patch.object(
            stt.os,
            "add_dll_directory",
            create=True,
            side_effect=[
                cuda_directory_handle,
                cudnn_directory_handle,
            ],
        ) as add_dll_directory, patch.object(
            stt.ctypes,
            "WinDLL",
            create=True,
            side_effect=[
                cublas_lt_handle,
                cublas_handle,
                cudnn_handle,
            ],
        ) as win_dll:
            stt._preload_gpu_runtime_dlls()
            stt._preload_gpu_runtime_dlls()

        self.assertEqual(
            find_dll.call_args_list,
            [
                call("cublasLt64_12.dll"),
                call("cublas64_12.dll"),
                call("cudnn64_9.dll"),
            ],
        )
        self.assertEqual(
            add_dll_directory.call_args_list,
            [
                call(str(cuda_directory)),
                call(str(cudnn_directory)),
            ],
        )
        self.assertEqual(
            win_dll.call_args_list,
            [
                call(str(dll_paths[0])),
                call(str(dll_paths[1])),
                call(str(dll_paths[2])),
            ],
        )
        self.assertTrue(stt._gpu_runtime_preloaded)

    def test_raises_when_a_required_runtime_dll_is_missing(self):
        with patch.object(stt.os, "name", "nt"), patch.object(
            stt,
            "_find_gpu_runtime_dll_path",
            return_value=None,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "cublasLt64_12.dll",
            ):
                stt._preload_gpu_runtime_dlls()

        self.assertFalse(stt._gpu_runtime_preloaded)