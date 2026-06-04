# 提示词恢复说明

若提示词管理里 **NSFW 为空**，请将原来的完整 SP `.txt` 文件放到本目录，例如：

- `segment_compress_v1_nsfw.txt`
- `segment_compress_v1_nsfw_en.txt`
- `history_merge_v1_nsfw.txt`
- `history_merge_v1_nsfw_en.txt`
- `segment_compress_v2_nsfw.txt`
- …（v2 同理）

然后在 `server` 目录执行：

```bash
python prompt_seed.py --dir seed_data/prompts
```

脚本会按 `split_prompt_content` 重新拆成 SFW + NSFW 并写回 MySQL。
