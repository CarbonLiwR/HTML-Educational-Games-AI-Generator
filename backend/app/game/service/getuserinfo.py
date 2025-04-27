import httpx
from fastapi import HTTPException


async def get_user_llm_info(*, user_token: str):
    """
    通过 user_token 查询用户的 api-key
    :param token: 用户 user_token
    :return: api-key 或 None
    """
    url = 'http://127.0.0.1:8000/api/v1/sys/users/me'
    headers = {
        'Authorization': f'Bearer {user_token}'  # 使用 f-string 格式化字符串
    }

    async with httpx.AsyncClient() as client:  # 创建异步客户端
        try:
            response = await client.get(url, headers=headers)  # 发送异步 GET 请求
            if response.status_code == 200:
                user_info= response.json()  # 假设返回的是 JSON 数据
                llm_models = user_info.get('data').get('llm_models')
                user_uuid = user_info.get('data').get('uuid')
                if len(llm_models) != 0:
                    provider = llm_models[0]
                    api_key = provider.get('api_key')
                    api_url = provider.get('api_url')
                    model_name = ""
                    for model in provider.get('models', []):

                        # 检查 status 是否为 1
                        if model.get('status') == 1:
                            model_name = model.get('name')
                            break
                    if not model_name:
                        raise HTTPException(status_code=400, detail="模型为空")
                else:
                    raise HTTPException(status_code=400, detail="模型为空")

                return {"api_url": api_url, "model_name": model_name, "api_key": api_key, "user_uuid": user_uuid}
            else:
                raise Exception(f"Failed to fetch user info: {response.status_code}")
        except httpx.HTTPError as e:
            raise Exception(f"HTTP error occurred: {e}")