"""TTS Manager for generating speech audio

基于火山引擎豆包语音合成 API v3
官方文档: https://www.volcengine.com/docs/6561/1598757

停顿支持：
  豆包 TTS 2.0 不支持 SSML <break> 标签，
  本模块通过文本拆分 + 静音拼接实现停顿。
  在文本中使用 [pause:2s] 或 [pause:500ms] 标记停顿位置。
  示例: "你好[pause:2s]这是一个测试[pause:500ms]继续说"
"""

import hashlib
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Tuple, Optional, List
import requests
from pydub import AudioSegment

from src.config import Config
from src.audio_silence_guard import (
    analyze_tts_silence,
    append_shadow_log,
    compress_internal_silences,
)

logger = logging.getLogger(__name__)


class TTSGenerationError(RuntimeError):
    """Raised when the configured TTS voice cannot generate usable audio."""


DEFAULT_TTS_PROVIDER = "doubao"
DEFAULT_DOUBAO_VOICE = "zh_male_jieshuoxiaoming_uranus_bigtts"
DEFAULT_ALIYUN_VOICE = "longcheng_v3"
DEFAULT_ALIYUN_MODEL = "cosyvoice-v3-flash"
DEFAULT_TTS_VOICE_ALIASES: dict[str, tuple[str, str]] = {
    "yingyujiaoxue": ("doubao", "zh_female_yingyujiaoxue_uranus_bigtts"),
    "longcheng": ("aliyun", "longcheng_v3"),
    "longhua": ("aliyun", "longhua_v3"),
    "longwan": ("aliyun", "longwan_v3"),
    "longxiaochun": ("aliyun", "longxiaochun_v3"),
    "longshuo": ("aliyun", "longshuo_v3"),
    "longxiu": ("aliyun", "longxiu_v3"),
    "longmiao": ("aliyun", "longmiao_v3"),
    "longyuan": ("aliyun", "longyuan_v3"),
    "xiaotian": ("doubao", "zh_male_taocheng_uranus_bigtts"),
    "xiaotian_2": ("doubao", "zh_male_taocheng_uranus_bigtts"),
    "yunzhou": ("doubao", "zh_male_m191_uranus_bigtts"),
    "yunzhou_2": ("doubao", "zh_male_m191_uranus_bigtts"),
    "liufei": ("doubao", "zh_male_liufei_uranus_bigtts"),
    "liu_fei": ("doubao", "zh_male_liufei_uranus_bigtts"),
    "liufei_2": ("doubao", "zh_male_liufei_uranus_bigtts"),
    "jieshuoxiaoming": ("doubao", "zh_male_jieshuoxiaoming_uranus_bigtts"),
    "qingshuangnanda": ("doubao", "zh_male_qingshuangnanda_uranus_bigtts"),
    "cancan": ("doubao", "zh_female_cancan_uranus_bigtts"),
    "linjianvhai": ("doubao", "zh_female_linjianvhai_uranus_bigtts"),
    "qingxinnvsheng": ("doubao", "zh_female_qingxinnvsheng_uranus_bigtts"),
    "zhixingnv": ("doubao", "zh_female_zhixingnv_uranus_bigtts"),
}


def _normalize_voice_alias(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def _load_tts_voice_aliases() -> dict[str, tuple[str, str]]:
    aliases = dict(DEFAULT_TTS_VOICE_ALIASES)
    alias_paths = [
        Config.ROOT_DIR / "tts_voice_aliases.json",
        Config.ROOT_DIR / "lecture_pipeline" / "tts_voice_aliases.json",
    ]

    for alias_path in alias_paths:
        if not alias_path.exists():
            continue
        try:
            data = json.loads(alias_path.read_text(encoding="utf-8"))
            for alias, cfg in data.get("aliases", {}).items():
                provider = str(cfg.get("provider", "")).strip().lower()
                voice = str(cfg.get("voice", "")).strip()
                if provider in {"aliyun", "doubao"} and voice:
                    aliases[_normalize_voice_alias(alias)] = (provider, voice)
        except Exception as e:
            logger.warning(f"⚠️  Failed to load TTS voice aliases from {alias_path}: {e}")

    # Also recognize the full voice ids in the table so provider mismatches are caught early.
    for provider, voice in list(aliases.values()):
        aliases[_normalize_voice_alias(voice)] = (provider, voice)
    return aliases


TTS_VOICE_ALIASES = _load_tts_voice_aliases()


def _load_default_voice_alias() -> Optional[tuple[str, str]]:
    """Load the default voice alias from tts_voice_aliases.json"""
    alias_paths = [
        Config.ROOT_DIR / "tts_voice_aliases.json",
        Config.ROOT_DIR / "lecture_pipeline" / "tts_voice_aliases.json",
    ]

    for alias_path in alias_paths:
        if not alias_path.exists():
            continue
        try:
            data = json.loads(alias_path.read_text(encoding="utf-8"))
            default_cfg = data.get("default", {})
            provider = str(default_cfg.get("provider", "")).strip().lower()
            voice = str(default_cfg.get("voice", "")).strip()
            if provider in {"aliyun", "doubao"} and voice:
                logger.info(f"📖 Loaded default TTS voice from {alias_path}: {provider}/{voice}")
                return (provider, voice)
        except Exception as e:
            logger.warning(f"⚠️  Failed to load default TTS voice from {alias_path}: {e}")

    return None


def resolve_tts_config(provider: Optional[str] = None, voice: Optional[str] = None) -> tuple[str, str]:
    """Resolve render-time TTS provider and voice.

    Defaults to the voice specified in tts_voice_aliases.json's "default" field,
    or falls back to Doubao / zh_male_jieshuoxiaoming_uranus_bigtts if no default is configured.
    Short aliases such as "liufei" are resolved before provider inference.
    If only a Doubao-style voice id is provided, infer Doubao so render callers
    can set a single field.
    """
    provider = (provider or "auto").strip().lower()
    voice = (voice or "").strip()

    # If no voice specified, check for default alias in JSON config
    if not voice:
        default_alias = _load_default_voice_alias()
        if default_alias:
            default_provider, default_voice = default_alias
            # If provider was explicitly set and conflicts, raise error
            if provider != "auto" and provider != default_provider:
                raise ValueError(
                    f"Default TTS voice maps to provider={default_provider}, "
                    f"but provider={provider} was requested"
                )
            provider = default_provider
            voice = default_voice
            logger.info(f"🎯 Using default TTS voice: {provider}/{voice}")

    voice_alias = TTS_VOICE_ALIASES.get(_normalize_voice_alias(voice)) if voice else None
    if voice_alias:
        alias_provider, alias_voice = voice_alias
        if provider != "auto" and provider != alias_provider:
            raise ValueError(
                f"TTS voice alias '{voice}' maps to provider={alias_provider}, "
                f"but provider={provider} was requested"
            )
        provider = alias_provider
        voice = alias_voice

    if provider == "auto":
        provider = "doubao" if voice.startswith("zh_") else DEFAULT_TTS_PROVIDER

    if provider not in {"aliyun", "doubao"}:
        raise ValueError(f"Unsupported TTS provider: {provider}")

    if not voice:
        voice = DEFAULT_ALIYUN_VOICE if provider == "aliyun" else DEFAULT_DOUBAO_VOICE

    return provider, voice


class DoubaoDriver:
    """
    Doubao TTS API driver (v3)
    
    基于火山引擎豆包语音合成 API v3
    支持豆包语音合成模型 2.0 (seed-tts-2.0)
    """
    
    def __init__(
        self,
        voice: Optional[str] = None,
        request_timeout: float = 30,
        speech_rate: Optional[float] = None,
    ):
        self.appid = Config.TTS_APPID
        self.token = Config.TTS_TOKEN
        self.cluster = Config.TTS_CLUSTER
        self.api_url = Config.TTS_API_URL
        self.default_voice = voice or Config.TTS_DEFAULT_VOICE
        self.request_timeout = request_timeout
        # 用户指定的语速倍率（1.0 = 现有默认），None 表示不调整
        self.speech_rate = speech_rate
        
        if not self.appid or not self.token:
            logger.warning("⚠️  Doubao TTS credentials not configured.")
            self.mock_mode = True
        else:
            self.mock_mode = False
            logger.info(f"✅ Doubao TTS initialized")
            logger.info(f"   Voice: {self.default_voice}")
            logger.info(f"   Cluster: {self.cluster}")
        
        # TTSManager owns retries so failures are visible and bounded.
        self.session = requests.Session()
    
    def generate(self, text: str, mode: str = "normal", prev_text: str = None) -> Tuple[str, float]:
        """
        Generate TTS audio
        
        Args:
            text: Text to convert to speech
            mode: Speech mode
            prev_text: 上一段 narration 文本，用于引用上文保持语气连贯
        
        Returns:
            Tuple of (audio_file_path, duration_in_seconds)
        """
        if self.mock_mode:
            raise TTSGenerationError("Doubao TTS credentials are not configured")
        
        # 检查是否包含 [pause:...] 标记
        if re.search(r'\[pause:\d+(?:\.\d+)?(?:s|ms)\]', text):
            return self._generate_with_pauses(text, mode, prev_text)
        
        return self._generate_single(text, mode, prev_text)
    
    def _generate_with_pauses(self, text: str, mode: str, prev_text: str = None) -> Tuple[str, float]:
        """
        处理含 [pause:Xs] / [pause:Xms] 标记的文本
        
        拆分文本 → 逐段生成音频 → 中间插入静音 → 拼接导出
        """
        # 解析文本段和停顿
        pattern = r'\[pause:(\d+(?:\.\d+)?)(s|ms)\]'
        segments = []  # [(type, value)] type='text'|'pause'
        
        last_end = 0
        for m in re.finditer(pattern, text):
            # 前面的文本
            before = text[last_end:m.start()].strip()
            if before:
                segments.append(('text', before))
            
            # 停顿时长（统一为毫秒）
            val = float(m.group(1))
            unit = m.group(2)
            pause_ms = int(val * 1000) if unit == 's' else int(val)
            pause_ms = min(pause_ms, 10000)  # 上限 10 秒
            segments.append(('pause', pause_ms))
            
            last_end = m.end()
        
        # 最后一段文本
        tail = text[last_end:].strip()
        if tail:
            segments.append(('text', tail))
        
        if not segments:
            raise TTSGenerationError("Cannot generate Doubao TTS for empty text")
        
        logger.info(f"🔀 Pause mode: {len(segments)} segments")
        
        # 逐段生成
        combined = AudioSegment.empty()
        for seg_type, seg_value in segments:
            if seg_type == 'pause':
                combined += AudioSegment.silent(duration=seg_value)
                logger.info(f"   ⏸️  Pause {seg_value}ms")
            else:
                # 生成这段文字的音频
                audio_path, dur = self._generate_single(seg_value, mode, prev_text)
                try:
                    chunk = AudioSegment.from_file(audio_path)
                    combined += chunk
                    logger.info(f"   🎙️  Text ({dur:.1f}s): {seg_value[:30]}...")
                except Exception as e:
                    raise TTSGenerationError(f"Failed to load generated Doubao chunk: {e}") from e
        
        # 导出拼接后的音频（使用唯一文件名避免并发竞争）
        cache_dir = Config.CACHE_DIR / "tts"
        fingerprint = self._get_fingerprint(text, mode)
        # 添加进程ID和时间戳确保并发安全
        unique_suffix = f"{os.getpid()}_{int(time.time() * 1000) % 10000}"
        audio_path = cache_dir / f"{fingerprint}_combined_{unique_suffix}.wav"
        combined.export(str(audio_path), format="wav")
        
        duration = len(combined) / 1000.0
        logger.info(f"✅ Combined audio: {duration:.2f}s -> {audio_path.name}")
        
        return str(audio_path), duration
    
    def _generate_single(self, text: str, mode: str = "normal", prev_text: str = None) -> Tuple[str, float]:
        """
        Generate TTS audio for a single text segment (no pause markers)
        """
        try:
            # Prepare request
            import uuid
            import base64
            
            headers = {
                "X-Api-App-Id": self.appid,
                "X-Api-Access-Key": self.token,
                "X-Api-Resource-Id": self.cluster,
                "X-Api-Request-Id": str(uuid.uuid4()),
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate",
            }
            
            # Get voice parameters based on mode
            speech_rate = self._get_speech_rate_for_mode(mode)
            loudness_rate = self._get_loudness_rate_for_mode(mode)
            context_texts = self._get_context_texts_for_mode(mode, prev_text)
            
            # 构建 additions 参数
            additions = {
                # 移除 silence_duration，让 TTS 自然结束，避免结尾爆音
                # "silence_duration": 125,      # 这个参数会在结尾添加静音，可能导致爆音
                "enable_latex_tn": True,        # 启用 LaTeX 文本归一化
                "disable_markdown_filter": True, # 开启 markdown 解析过滤
                "pure_english_opt": 0           # 纯英文优化：0=关闭，1=开启
            }
            
            # 构建请求体（严格按照官方文档格式）
            payload = {
                "user": {
                    "uid": "manim_user"
                },
                "req_params": {
                    "text": text,
                    "speaker": self.default_voice,
                    "audio_params": {
                        "format": "wav",              # 音频编码格式：mp3/ogg_opus/pcm/wav
                        "sample_rate": 24000,         # 音频采样率：8000/16000/22050/24000/32000/44100/48000
                        "speech_rate": speech_rate,   # 语速：-50 到 100
                        "loudness_rate": loudness_rate # 音量：-50 到 100
                    },
                    "additions": json.dumps(additions)
                }
            }
            
            # 添加 context_texts 指令（仅TTS 2.0支持）
            if context_texts:
                payload["req_params"]["context_texts"] = context_texts
            
            # Make API call
            logger.info(f"🎙️  Calling Doubao API")
            logger.info(f"   Text: {text[:50]}{'...' if len(text) > 50 else ''}")
            if context_texts:
                logger.info(f"   Mode: {mode} (指令: {context_texts[0]})")
            else:
                logger.info(f"   Mode: {mode} (speech_rate={speech_rate}, loudness_rate={loudness_rate})")
            
            response = self.session.post(
                self.api_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.request_timeout
            )
            
            # 获取 logid 用于问题定位
            logid = response.headers.get('X-Tt-Logid', 'N/A')
            logger.info(f"   Logid: {logid}")
            
            if response.status_code != 200:
                raise TTSGenerationError(
                    f"Doubao HTTP {response.status_code}, logid={logid}, "
                    f"response={response.text[:200]}"
                )
            
            # Parse streaming response
            # 豆包 API 返回的是流式数据，每行一个 JSON
            audio_data = bytearray()
            line_count = 0
            success = False
            
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                
                line_count += 1
                try:
                    j = json.loads(line)
                    code = j.get("code")
                    
                    # 检查是否是结束标记
                    if code == 20000000:
                        logger.info(f"✅ Audio synthesis completed successfully")
                        success = True
                        break
                    
                    # 检查错误
                    if code != 0:
                        error_msg = j.get("message", "Unknown error")
                        logger.error(f"❌ API returned error code {code}: {error_msg}")
                        logger.error(f"   Logid: {logid}")
                        
                        # 处理特定错误
                        if code == 40402003:
                            logger.error("   Text length exceeded limit")
                        elif code == 45000000:
                            logger.error("   Speaker permission denied or quota exceeded")
                        elif code == 55000000:
                            logger.error("   Server error")
                        
                        raise TTSGenerationError(
                            f"Doubao API code={code}, message={error_msg}, logid={logid}"
                        )
                    
                    # 提取音频数据
                    if "data" in j and j["data"]:
                        audio_chunk = base64.b64decode(j["data"])
                        audio_data.extend(audio_chunk)
                        
                except json.JSONDecodeError:
                    # 某些行可能不是 JSON（如空行）
                    continue
                except TTSGenerationError:
                    raise
                except Exception as e:
                    logger.warning(f"⚠️  Failed to parse line {line_count}: {e}")
                    continue
            
            if not audio_data:
                raise TTSGenerationError(f"Doubao returned no audio data, logid={logid}")
            
            if not success:
                raise TTSGenerationError(f"Doubao stream ended without completion marker, logid={logid}")
            
            logger.info(f"✅ Received {len(audio_data)} bytes from {line_count} chunks")
            
            # Save audio file
            cache_dir = Config.CACHE_DIR / "tts"
            fingerprint = self._get_fingerprint(text, mode)
            audio_path = cache_dir / f"{fingerprint}.wav"
            
            # 原子写入 (参考 main_v5 的最佳实践)
            temp_path = audio_path.with_suffix(".tmp")
            with open(temp_path, 'wb') as f:
                f.write(audio_data)
                f.flush()
                import os
                os.fsync(f.fileno())  # 确保写入磁盘
            
            # 确保覆盖
            if audio_path.exists():
                audio_path.unlink()
            temp_path.rename(audio_path)
            
            # 强制垃圾回收，释放文件句柄
            import gc
            gc.collect()
            
            # 短暂延迟，确保文件系统同步
            time.sleep(0.05)
            
            # Calculate duration
            duration = self._get_audio_duration(str(audio_path))
            
            logger.info(f"✅ TTS generated successfully")
            logger.info(f"   Duration: {duration:.2f}s")
            logger.info(f"   File: {audio_path.name}")
            
            return str(audio_path), duration
            
        except requests.exceptions.Timeout:
            raise TTSGenerationError(f"Doubao TTS timeout ({self.request_timeout:.0f}s)")
        except requests.exceptions.RequestException as e:
            raise TTSGenerationError(f"Doubao TTS request failed: {e}") from e
        except Exception as e:
            if isinstance(e, TTSGenerationError):
                raise
            raise TTSGenerationError(f"Doubao TTS generation failed: {e}") from e
    
    def _generate_mock(self, text: str) -> Tuple[str, float]:
        """Generate mock audio (silent) for testing"""
        # Estimate duration: ~5 characters per second for Chinese
        duration = max(1.0, len(text) / 5.0)
        
        # Create silent audio
        silent = AudioSegment.silent(duration=int(duration * 1000))
        
        cache_dir = Config.CACHE_DIR / "tts"
        fingerprint = self._get_fingerprint(text, "mock")
        audio_path = cache_dir / f"{fingerprint}.wav"
        
        silent.export(str(audio_path), format="wav")
        
        logger.info(f"🔇 Mock TTS: {text[:30]}... ({duration:.2f}s)")
        return str(audio_path), duration
    
    def _get_speech_rate_for_mode(self, mode: str) -> int:
        """
        Get speech rate based on mode
        
        范围：-50 到 100
        - 100 代表 2.0 倍速
        - 0 代表正常语速
        - -50 代表 0.5 倍速
        
        注意：当使用 context_texts 指令时，此参数作为基础调整
        """
        speech_rate_map = {
            "intro": -12,
            "normal": -12,
            "strict": -12,
            "fast": -12,
            "slow": -12,
            "encouraging": -12,
            "dictation": -12,
            "inspiring": -12,
        }
        base = speech_rate_map.get(mode, -5)

        # 用户语速倍率换算成 API 偏移量叠加在 mode 基础语速上：
        # 倍率 1.0 = 偏移 0（与历史默认行为一致），1.2 = +20，0.8 = -20
        if self.speech_rate is not None and self.speech_rate != 1.0:
            base = base + int(round((self.speech_rate - 1.0) * 100))

        return max(-50, min(100, base))
    
    def _get_loudness_rate_for_mode(self, mode: str) -> int:
        """
        Get loudness (volume) based on mode
        
        范围：-50 到 100
        - 100 代表 2.0 倍音量
        - 0 代表正常音量
        - -50 代表 0.5 倍音量
        
        注意：当使用 context_texts 指令时，此参数作为基础调整
        """
        loudness_rate_map = {
            "intro": 0,          # Normal volume
            "normal": 0,         # Normal volume
            "strict": -10,       # Slightly quieter for serious content
            "fast": 0,           # Normal volume
            "slow": 0,           # Normal volume
            "encouraging": 10,   # Slightly louder for encouragement
            "dictation": 0,      # Normal volume
            "inspiring": 15,     # Louder for inspiring speech
        }
        return loudness_rate_map.get(mode, 0)
    
    def _get_context_texts_for_mode(self, mode: str, prev_text: str = None) -> Optional[list]:
        """
        Get context_texts instruction for mode (TTS 2.0 feature)
        
        结合两个豆包 2.0 功能：
        1. 语音指令：控制整体语气风格
        2. 引用上文：承接前一段的语境，保持语气连贯
        
        prev_text: 上一段 narration 的最后一句话，用于引用上文
        """
        # 基础角色指令（更具体，减少模型自由发挥导致的语气波动）
        base_instructions = {
            "intro": "你是一位经验丰富的高中数学老师，正在课堂上开始讲解一道题目，语气平稳温和，充满耐心",
            "normal": "你是一位经验丰富的高中数学老师，正在课堂上给学生讲解数学题，语气始终平稳温和，语速适中，保持耐心和鼓励的态度，不要有明显的情绪波动，不要因为问句而升高语调，始终保持平稳的叙述语气",
            "strict": "你是一位严谨的数学老师，正在强调一个重要的知识点，语气认真但不严厉",
            "fast": "你是一位数学老师，这部分内容比较简单，可以稍微加快语速",
            "slow": "你是一位数学老师，这部分内容是难点，请放慢语速，让学生能跟上",
            "encouraging": "你是一位数学老师，学生刚做对了一步，用温和鼓励的语气继续引导",
            "dictation": "你是一位数学老师，正在清晰地读出每个关键步骤",
            "inspiring": "你是一位充满激情的演讲者，正在做一场鼓舞人心的演讲",
        }
        
        instruction = base_instructions.get(mode, base_instructions["normal"])
        
        # 如果有上一段文本，加入引用上文
        if prev_text:
            # 取最后一句话（按句号/问号/感叹号分割）
            import re
            sentences = re.split(r'[。！？]', prev_text)
            last_sentence = ''
            for s in reversed(sentences):
                s = s.strip()
                if len(s) > 5:  # 至少 5 个字才算有效句子
                    last_sentence = s
                    break
            
            if last_sentence:
                # 用 [#上文] 格式引用，让模型承接语境
                instruction = f"{instruction}。上一句话是：{last_sentence}"
        
        return [instruction]
    
    def _get_fingerprint(self, text: str, mode: str) -> str:
        """Generate fingerprint for caching"""
        key = f"{text}_{mode}_{self.default_voice}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def _generate_room_tone(self, duration_ms: int = 1000, volume_db: float = -40.0) -> AudioSegment:
        """
        生成 Room Tone（环境底噪）
        
        Room Tone 是专业视频制作中用来保持音频连续性的技术。
        在语音片段之间添加低音量的环境音，让听感更自然连续。
        
        Args:
            duration_ms: 时长（毫秒）
            volume_db: 音量（dB），推荐 -40 到 -50
        
        Returns:
            AudioSegment: 生成的 room tone
        """
        from pydub import AudioSegment
        from pydub.generators import WhiteNoise
        
        # 生成白噪音作为 room tone
        room_tone = WhiteNoise().to_audio_segment(duration=duration_ms)
        
        # 降低音量到环境音水平
        room_tone = room_tone + volume_db
        
        return room_tone
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds"""
        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            return 0.0


class CosyVoiceDriver:
    """
    阿里云百炼 CosyVoice v3 TTS driver
    
    优势：音色稳定性极好，分段生成拼接后语气连贯
    """
    
    def __init__(
        self,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speech_rate: Optional[float] = None,
        call_timeout: Optional[float] = None,
    ):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.model = model or DEFAULT_ALIYUN_MODEL
        self.voice = voice or DEFAULT_ALIYUN_VOICE
        self.speech_rate = 0.9 if speech_rate is None else speech_rate
        # syn.call() 是阻塞式 websocket 调用，本身无超时；远端掉线会让主线程永久挂起。
        # 用守护线程 + join(timeout) 给当前音色明确失败，不做跨平台回退。
        self.call_timeout = (
            float(call_timeout)
            if call_timeout is not None
            else float(os.getenv("COSYVOICE_CALL_TIMEOUT", "60"))
        )

        if not self.api_key:
            logger.warning("⚠️  DASHSCOPE_API_KEY not configured. CosyVoice unavailable.")
            self.available = False
        else:
            self.available = True
            import dashscope
            dashscope.api_key = self.api_key
            dashscope.base_websocket_api_url = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference'
            logger.info(f"✅ CosyVoice initialized: {self.model} / {self.voice} / rate={self.speech_rate}")
    
    def generate(self, text: str, mode: str = "normal", prev_text: str = None) -> Tuple[str, float]:
        """Generate TTS audio using CosyVoice"""
        if not self.available:
            raise TTSGenerationError("DASHSCOPE_API_KEY is not configured")
        
        try:
            from dashscope.audio.tts_v2 import SpeechSynthesizer
            import threading

            # syn.call() 无内建超时，websocket 掉线会永久阻塞。放进守护线程跑，
            # 超时未返回就放弃该线程（随进程退出），由 TTSManager 重试当前音色。
            box: dict = {}

            def _worker():
                try:
                    syn = SpeechSynthesizer(
                        model=self.model,
                        voice=self.voice,
                        speech_rate=self.speech_rate,
                    )
                    box["data"] = syn.call(text)
                except Exception as e:  # noqa: BLE001 - 线程内异常透传给主线程处理
                    box["error"] = e

            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()
            worker.join(timeout=self.call_timeout)

            if worker.is_alive():
                raise TTSGenerationError(
                    f"CosyVoice timeout ({self.call_timeout:.0f}s), voice={self.voice}"
                )

            if "error" in box:
                raise TTSGenerationError(f"CosyVoice error: {box['error']}") from box["error"]

            audio_data = box.get("data")

            if not audio_data:
                raise TTSGenerationError(f"CosyVoice returned no audio, voice={self.voice}")

            # Save to cache
            cache_dir = Config.CACHE_DIR / "tts"
            fingerprint = self._get_fingerprint(text, mode)
            audio_path = cache_dir / f"{fingerprint}.wav"

            temp_path = audio_path.with_suffix(".tmp")
            with open(str(temp_path), 'wb') as f:
                f.write(audio_data)
                f.flush()
                os.fsync(f.fileno())
            if audio_path.exists():
                audio_path.unlink()
            temp_path.rename(audio_path)

            duration = self._get_audio_duration(str(audio_path))

            logger.info(f"✅ CosyVoice TTS: {duration:.2f}s - {text[:40]}...")
            return str(audio_path), duration

        except Exception as e:
            if isinstance(e, TTSGenerationError):
                raise
            raise TTSGenerationError(f"CosyVoice generation failed: {e}") from e
    
    def _get_fingerprint(self, text: str, mode: str) -> str:
        key = f"cosyvoice_{self.model}_{text}_{mode}_{self.voice}_{self.speech_rate}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def _get_audio_duration(self, audio_path: str) -> float:
        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception:
            return 0.0


class TTSManager:
    """TTS Manager with caching support"""
    
    def __init__(
        self,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
        retry_count: int = 2,
        speech_rate: Optional[float] = None,
    ):
        self.provider, self.voice = resolve_tts_config(provider, voice)
        self.retry_count = max(0, int(retry_count))
        # 语速倍率（0.5~2.0；1.0/None = 现有默认），越界裁剪
        if speech_rate is not None:
            speech_rate = max(0.5, min(2.0, float(speech_rate)))
        self.speech_rate = speech_rate

        if self.provider == "aliyun":
            # CosyVoice 的 speech_rate 是绝对倍率，历史默认 0.9；用户倍率在其上缩放
            driver_rate = 0.9 * speech_rate if speech_rate is not None else None
            self.driver = CosyVoiceDriver(voice=self.voice, speech_rate=driver_rate)
            logger.info(f"🎙️  TTS Engine: Aliyun CosyVoice v3 / {self.voice}")
        else:
            self.driver = DoubaoDriver(voice=self.voice, speech_rate=speech_rate)
            logger.info(f"🎙️  TTS Engine: Doubao / {self.voice}")
        if speech_rate is not None and speech_rate != 1.0:
            logger.info(f"🎙️  Speech rate: {speech_rate}x")
        
        self.cache_index_path = Config.CACHE_DIR / "tts" / "cache_index.json"
        self.failure_log_path = Config.CACHE_DIR / "tts" / "failures.jsonl"
        self.silence_guard_log_path = Config.CACHE_DIR / "tts" / "silence_guard.jsonl"
        self.silence_quarantine_dir = Config.CACHE_DIR / "tts" / "quarantine"
        self.cache_index = self._load_cache_index()
    
    def generate(self, text: str, mode: str = "normal", prev_text: str = None) -> Tuple[str, float]:
        """
        Generate TTS audio with caching
        
        Args:
            text: Text to convert to speech
            mode: Speech mode
            prev_text: 上一段 narration，用于引用上文保持语气连贯
        
        Returns:
            Tuple of (audio_file_path, duration_in_seconds)
        """
        # 缓存 key 需要包含 provider/voice/prev_text/语速，避免旧回退缓存、不同上下文或不同语速串音。
        # 语速为默认（None/1.0）时不带后缀，保持与既有缓存 key 兼容。
        rate_part = "" if (self.speech_rate is None or self.speech_rate == 1.0) else f"_{self.speech_rate}"
        cache_key = f"nofallback_v1_{self.provider}_{self.voice}_{text}_{mode}_{prev_text or ''}{rate_part}"
        fingerprint = self.driver._get_fingerprint(cache_key, mode)
        cached = self._get_from_cache(fingerprint)
        
        if cached:
            try:
                new_duration = self._enforce_silence_gate(cached[0], text, source="cache")
            except TTSGenerationError as e:
                # 缓存音频静音处理失败（极少见，如文件损坏）：失效后走重新生成
                logger.warning(f"⚠️  缓存 TTS 静音处理失败，索引失效并重新生成: {e}")
                self._invalidate_cache(fingerprint)
            else:
                if new_duration is not None:
                    # 缓存音频就地压缩过，更新索引时长，避免下次命中时偏移
                    self.cache_index[fingerprint]["duration"] = new_duration
                    self._save_cache_index()
                    cached = (cached[0], new_duration)
                logger.info(f"✅ TTS cache hit: {text[:30]}...")
                return cached
        
        attempts = self.retry_count + 1
        errors: list[str] = []
        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    f"🎙️  TTS attempt {attempt}/{attempts}: "
                    f"{self.provider}/{self.voice}"
                )
                audio_path, duration = self.driver.generate(text, mode, prev_text)
                self._validate_generated_audio(audio_path, duration)
                new_duration = self._enforce_silence_gate(audio_path, text, source="generated")
                if new_duration is not None:
                    duration = new_duration
                self._save_to_cache(fingerprint, audio_path, duration)
                return audio_path, duration
            except Exception as e:
                error_msg = str(e)
                errors.append(error_msg)
                logger.error(
                    f"❌ TTS attempt {attempt}/{attempts} failed "
                    f"({self.provider}/{self.voice}): {error_msg}"
                )
                if attempt < attempts:
                    time.sleep(min(1.5 * attempt, 5.0))

        self._record_failure(text, mode, prev_text, errors)
        raise TTSGenerationError(
            f"TTS failed after {attempts} attempts "
            f"provider={self.provider}, voice={self.voice}. Last error: {errors[-1]}"
        )
    
    def batch_generate(self, tasks: List[Tuple[str, str]], max_workers: int = 4) -> List[Tuple[str, float]]:
        """
        Generate multiple TTS audios in parallel
        
        Args:
            tasks: List of (text, mode) tuples
            max_workers: Maximum number of parallel workers
        
        Returns:
            List of (audio_path, duration) tuples
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        logger.info(f"🔄 Batch TTS generation: {len(tasks)} tasks with {max_workers} workers")
        
        results = []
        cache_hits = 0
        cache_misses = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(self.generate, text, mode): (text, mode)
                for text, mode in tasks
            }
            
            # Collect results
            for future in as_completed(future_to_task):
                text, mode = future_to_task[future]
                try:
                    audio_path, duration = future.result()
                    results.append((audio_path, duration))
                    
                    # Check if it was a cache hit
                    if "cache hit" in str(audio_path).lower():
                        cache_hits += 1
                    else:
                        cache_misses += 1
                        
                except Exception as e:
                    logger.error(f"❌ Batch TTS failed for '{text[:30]}...': {e}")
                    raise TTSGenerationError(
                        f"Batch TTS failed for '{text[:30]}...' "
                        f"provider={self.provider}, voice={self.voice}: {e}"
                    ) from e
        
        logger.info(f"✅ Batch TTS completed: {cache_hits} cache hits, {cache_misses} new generations")
        
        return results
    
    def _load_cache_index(self) -> dict:
        """Load cache index from disk"""
        if self.cache_index_path.exists():
            try:
                with open(self.cache_index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load cache index: {e}")
                return {}
        return {}
    
    def _save_cache_index(self):
        """Save cache index to disk"""
        try:
            with open(self.cache_index_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache_index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")
    
    def _get_from_cache(self, fingerprint: str) -> Optional[Tuple[str, float]]:
        """Get audio from cache (rejects silent/failed audio)"""
        if fingerprint in self.cache_index:
            entry = self.cache_index[fingerprint]
            audio_path = entry["path"]

            # Check if file exists
            if not Path(audio_path).exists():
                # 文件已删除，清理索引
                del self.cache_index[fingerprint]
                self._save_cache_index()
                return None

            # 静音检测：拒绝之前 TTS 失败缓存下来的静音文件
            try:
                with Path(audio_path).open("rb") as handle:
                    audio = AudioSegment.from_file(handle)
                if audio.rms == 0 and len(audio) > 500:
                    logger.warning(f"⚠ 缓存命中但音频静音，丢弃并重新生成: {audio_path}")
                    del self.cache_index[fingerprint]
                    self._save_cache_index()
                    return None
            except Exception:
                pass

            return audio_path, entry["duration"]

        return None
    
    def _save_to_cache(self, fingerprint: str, audio_path: str, duration: float):
        """Save audio to cache index (skip silent/failed audio)"""
        # 静音检测：静音文件不应缓存
        try:
            with Path(audio_path).open("rb") as handle:
                audio = AudioSegment.from_file(handle)
            if audio.rms == 0 and len(audio) > 500:
                logger.warning(f"⚠ 跳过缓存：音频文件静音 ({duration:.1f}s)，疑似 TTS 失败")
                return
        except Exception:
            pass

        self.cache_index[fingerprint] = {
            "path": audio_path,
            "duration": duration,
            "provider": self.provider,
            "voice": self.voice,
            "timestamp": time.time()
        }
        self._save_cache_index()

    def _validate_generated_audio(self, audio_path: str, duration: float):
        """Reject missing, empty, or silent generated audio before caching."""
        if not audio_path or not Path(audio_path).exists():
            raise TTSGenerationError(f"TTS returned missing audio file: {audio_path}")
        try:
            with Path(audio_path).open("rb") as handle:
                audio = AudioSegment.from_file(handle)
        except Exception as e:
            raise TTSGenerationError(f"TTS returned unreadable audio file: {audio_path}: {e}") from e
        actual_duration = len(audio) / 1000.0
        if actual_duration <= 0.1 or duration <= 0.1:
            raise TTSGenerationError(
                f"TTS returned too-short audio: reported={duration:.2f}s, actual={actual_duration:.2f}s"
            )
        if audio.rms == 0 and len(audio) > 500:
            raise TTSGenerationError(f"TTS returned silent audio: {audio_path}")

    def _record_failure(self, text: str, mode: str, prev_text: Optional[str], errors: list[str]):
        """Append a machine-readable failure record for agents and humans."""
        record = {
            "timestamp": time.time(),
            "provider": self.provider,
            "voice": self.voice,
            "mode": mode,
            "retry_count": self.retry_count,
            "attempts": self.retry_count + 1,
            "text": text,
            "prev_text": prev_text,
            "errors": errors,
        }
        try:
            self.failure_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.failure_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.error(f"🧾 TTS failure recorded: {self.failure_log_path}")
        except Exception as e:
            logger.error(f"Failed to record TTS failure: {e}")

    def _enforce_silence_gate(self, audio_path: str, text: str, source: str) -> Optional[float]:
        """Compress abnormal long internal silence in place.

        Deterministic TTS voices reproduce the same silence on every retry, so
        rejecting-and-retry is a dead end. Instead, cap each over-long internal
        silence to a natural pause length and accept the clip. The original
        bytes are quarantined first for diagnosis.

        Returns the new duration in seconds when the audio was compressed, or
        ``None`` when no compression was needed.
        """
        try:
            report = analyze_tts_silence(audio_path, text)
        except Exception as e:
            raise TTSGenerationError(f"TTS silence quality check failed: {e}") from e

        if not report.get("would_compress"):
            return None

        quarantined = self._quarantine_audio(audio_path)
        try:
            compression = compress_internal_silences(audio_path, text)
        except Exception as e:
            raise TTSGenerationError(f"TTS silence compression failed: {e}") from e

        append_shadow_log(
            self.silence_guard_log_path,
            report,
            source=source,
            action="compressed",
            provider=self.provider,
            voice=self.voice,
            cap_ms=compression.get("cap_ms"),
            original_duration_ms=compression.get("original_duration_ms"),
            new_duration_ms=compression.get("duration_ms"),
            capped_silences=compression.get("capped_silences", []),
        )
        logger.info(
            "🔧 TTS 静音压缩：longest="
            f"{report['longest_internal_silence_ms']}ms -> cap={compression.get('cap_ms')}ms, "
            f"source={source}, quarantine={quarantined}, text={text[:50]}..."
        )
        new_duration_ms = compression.get("duration_ms")
        return new_duration_ms / 1000.0 if new_duration_ms is not None else None

    def _invalidate_cache(self, fingerprint: str) -> None:
        if fingerprint in self.cache_index:
            del self.cache_index[fingerprint]
            self._save_cache_index()

    def _quarantine_audio(self, audio_path: str) -> str:
        """Copy rejected bytes for diagnosis; the driver may overwrite its normal path on retry."""
        try:
            source = Path(audio_path)
            self.silence_quarantine_dir.mkdir(parents=True, exist_ok=True)
            suffix = source.suffix or ".bin"
            target = self.silence_quarantine_dir / (
                f"{source.stem}_{int(time.time() * 1000)}{suffix}"
            )
            shutil.copy2(source, target)
            return str(target)
        except Exception as e:
            logger.warning(f"⚠️  无法保存异常 TTS 副本：{e}")
            return "<quarantine failed>"
