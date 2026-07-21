import base64
import io
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from meme_generator import (
    DeserializeError,
    ImageAssetMissing,
    ImageDecodeError,
    ImageEncodeError,
    ImageNumberMismatch,
    Meme,
    MemeFeedback,
    TextNumberMismatch,
    TextOverLength,
    get_memes,
)
from meme_generator import Image as MemeImage
from meme_generator.resources import check_resources

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(APP_DIR), static_url_path="")

# 启用CORS支持跨域请求
CORS(app, supports_credentials=True)

_template_map: dict[str, Meme] = {}
_template_list: list[dict] = []


def load_templates():
    """加载所有表情包模板"""
    global _template_map, _template_list
    try:
        logger.info("正在检查模板资源（首次启动可能需要几分钟）...")
        check_resources()
        logger.info("模板资源检查完成")
        memes = get_memes()
        _template_map.clear()
        _template_list.clear()
        
        for meme in memes:
            params = meme.info.params
            keywords = list(meme.info.keywords)
            _template_map[meme.key] = meme
            
            for kw in keywords:
                _template_map.setdefault(kw, meme)
                
            _template_list.append({
                "key": meme.key,
                "keywords": keywords,
                "min_images": params.min_images,
                "max_images": params.max_images,
                "min_texts": params.min_texts,
                "max_texts": params.max_texts,
                "default_texts": list(params.default_texts),
            })
            
        _template_list.sort(key=lambda x: x["key"])
        logger.info(f"成功加载 {len(_template_list)} 个模板，{len(_template_map)} 个关键词")
    except Exception as e:
        logger.error(f"加载模板失败: {str(e)}")
        raise


def fetch_qq_avatar(qq: str) -> bytes | None:
    """获取QQ头像"""
    if not qq or not qq.isdigit():
        logger.warning(f"无效的QQ号: {qq}")
        return None
        
    url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={qq}&spec=640"
    try:
        with urlopen(url, timeout=8) as resp:
            data = resp.read()
            if len(data) > 100:  # 简单验证图片有效性
                return data
            logger.warning(f"获取到的头像数据过小: {len(data)} bytes")
            return None
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        logger.warning(f"获取QQ头像失败 {qq}: {str(e)}")
        return None


def get_meme_by_keyword(keyword: str) -> Meme | None:
    """根据关键词获取模板"""
    return _template_map.get(keyword)


def format_error(result) -> str:
    """格式化错误信息"""
    if isinstance(result, ImageAssetMissing):
        return "模板资源缺失，请检查 meme_generator 资源包"
    if isinstance(result, ImageDecodeError):
        return f"图片解码失败: {result.error}"
    if isinstance(result, ImageEncodeError):
        return f"图片编码失败: {result.error}"
    if isinstance(result, DeserializeError):
        return f"参数解析失败: {result.error}"
    if isinstance(result, ImageNumberMismatch):
        need = f"{result.min}~{result.max}" if result.min != result.max else str(result.min)
        return f"图片数量不符，需要 {need} 张，实际 {result.actual} 张"
    if isinstance(result, TextNumberMismatch):
        need = f"{result.min}~{result.max}" if result.min != result.max else str(result.min)
        return f"文字数量不符，需要 {need} 段，实际 {result.actual} 段"
    if isinstance(result, TextOverLength):
        return "文字过长，请缩短后重试"
    if isinstance(result, MemeFeedback):
        return str(result.feedback)
    return "生成失败，请换一个模板试试"


@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理"""
    logger.error(f"服务器异常: {str(e)}", exc_info=True)
    return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500


@app.errorhandler(404)
def not_found(e):
    """404处理"""
    return jsonify({"error": "接口不存在"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    """405处理"""
    return jsonify({"error": "请求方法不允许"}), 405


@app.route("/")
def index():
    """首页"""
    index_path = APP_DIR / "index.html"
    if index_path.exists():
        return send_file(str(index_path))
    return jsonify({"message": "表情包生成器 API 服务运行中"}), 200


@app.route("/api/qq-avatar/<qq>")
def get_qq_avatar(qq):
    """获取QQ头像代理"""
    logger.info(f"获取QQ头像请求: {qq}")
    
    if not qq or not qq.isdigit():
        logger.warning(f"无效的QQ号: {qq}")
        return jsonify({"error": "无效的QQ号"}), 400
    
    try:
        # 使用腾讯QQ头像API
        url = f"https://q1.qlogo.cn/g?b=qq&nk={qq}&s=100"
        logger.info(f"请求URL: {url}")
        
        # 添加完整的请求头
        from urllib.request import Request
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.qq.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        })
        
        with urlopen(req, timeout=10) as response:
            avatar_data = response.read()
            logger.info(f"成功获取头像，大小: {len(avatar_data)} bytes")
            return send_file(
                io.BytesIO(avatar_data),
                mimetype='image/jpeg'
            )
    except (HTTPError, URLError, Exception) as e:
        logger.error(f"获取QQ头像失败 ({qq}): {str(e)}")
        return jsonify({"error": "无法获取头像"}), 400




@app.route("/api/health")
def health():
    """健康检查接口"""
    return jsonify({
        "status": "ok",
        "templates": len(_template_list),
        "keywords": len(_template_map)
    }), 200


@app.route("/api/templates")
def list_templates():
    """获取模板列表"""
    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "templates": _template_list,
            "total": len(_template_list)
        }
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    """生成表情包"""
    try:
        data = request.get_json() or {}
        keyword = (data.get("keyword") or "").strip()
        
        if not keyword:
            return jsonify({"error": "请指定模板关键词"}), 400
            
        meme = get_meme_by_keyword(keyword)
        if not meme:
            return jsonify({"error": f"未找到模板: {keyword}"}), 404
            
        params = meme.info.params
        
        # 处理文字参数
        texts = data.get("texts") or []
        if isinstance(texts, str):
            texts = [t.strip() for t in texts.split() if t.strip()]
        texts = [str(t).strip() for t in texts if str(t).strip()]
        
        # 补充默认文字
        if len(texts) < params.min_texts and params.default_texts:
            default_count = params.min_texts - len(texts)
            texts.extend(params.default_texts[:default_count])
            
        # 严格检查文字数量
        if len(texts) < params.min_texts:
            return jsonify({
                "error": f"文字数量不足，至少需要 {params.min_texts} 段文字"
            }), 400
            
        texts = texts[:params.max_texts]
        
        # 处理图片参数
        meme_images: list[MemeImage] = []
        images = data.get("images") or []
        
        if isinstance(images, list):
            for img in images:
                if not isinstance(img, dict):
                    continue
                    
                img_type = img.get("type", "")
                name = str(img.get("name", "image"))
                
                try:
                    if img_type == "base64":
                        raw = img.get("data", "")
                        if "," in raw:
                            raw = raw.split(",", 1)[1]
                        img_data = base64.b64decode(raw)
                        if len(img_data) > 100:
                            meme_images.append(MemeImage(name, img_data))
                            
                    elif img_type == "qq":
                        qq = str(img.get("qq", "")).strip()
                        if qq and qq.isdigit():
                            avatar = fetch_qq_avatar(qq)
                            if avatar:
                                meme_images.append(MemeImage(f"用户{qq}", avatar))
                                
                    elif img_type == "url":
                        img_url = str(img.get("url", "")).strip()
                        if img_url and img_url.startswith(("http://", "https://")):
                            with urlopen(img_url, timeout=10) as resp:
                                img_data = resp.read()
                                if len(img_data) > 100:
                                    meme_images.append(MemeImage(name, img_data))
                except Exception as e:
                    logger.warning(f"处理图片失败: {str(e)}")
                    continue
        
        # 严格检查图片数量
        meme_images = meme_images[:params.max_images]
        if len(meme_images) < params.min_images:
            return jsonify({
                "error": f"图片数量不足，至少需要 {params.min_images} 张图片"
            }), 400
        
        # 生成表情包
        logger.info(f"开始生成表情包: {keyword}, 图片数: {len(meme_images)}, 文字数: {len(texts)}")
        result = meme.generate(meme_images, texts, {})
        
        if isinstance(result, bytes):
            # 自动识别图片类型
            mime = "image/png"
            if result.startswith(b"\xff\xd8"):
                mime = "image/jpeg"
            elif result.startswith(b"GIF8"):
                mime = "image/gif"
                
            logger.info(f"表情包生成成功，大小: {len(result)} bytes")
            return send_file(
                io.BytesIO(result),
                mimetype=mime,
                download_name=f"meme_{keyword}.png"
            )
            
        error_msg = format_error(result)
        logger.warning(f"表情包生成失败: {error_msg}")
        return jsonify({"error": error_msg}), 400
        
    except Exception as e:
        logger.error(f"生成表情包异常: {str(e)}", exc_info=True)
        return jsonify({"error": f"生成失败: {str(e)}"}), 500


@app.route("/api/avatar/<qq>")
def avatar(qq: str):
    """获取QQ头像接口"""
    if not qq or not qq.isdigit():
        return jsonify({"error": "无效的QQ号"}), 400
        
    avatar_data = fetch_qq_avatar(qq)
    if avatar_data:
        return send_file(
            io.BytesIO(avatar_data),
            mimetype="image/jpeg",
            download_name=f"avatar_{qq}.jpg"
        )
    return jsonify({"error": "头像获取失败"}), 404


if __name__ == "__main__":
    load_templates()
    logger.info("表情包生成器服务启动中...")
    logger.info(f"已加载 {len(_template_list)} 个模板，{len(_template_map)} 个关键词")
    logger.info("服务地址: http://localhost:7861")
    logger.info("按 Ctrl+C 停止服务")
    app.run(host="0.0.0.0", port=7861, debug=False, threaded=True)
