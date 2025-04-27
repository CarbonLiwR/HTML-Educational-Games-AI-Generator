// src/components/ChatLayout.jsx
import React, {useEffect, useRef, useState} from "react";
import {Layout, Button, Input, Typography, Space, List, Splitter, Spin, Flex, message, Popconfirm, Modal} from "antd";
import {EditOutlined, MailOutlined} from "@ant-design/icons";
import {getToken} from "../../utils/auth.ts";
import {CaretRightOutlined, VerticalAlignBottomOutlined,ClearOutlined} from "@ant-design/icons";
import axios from "axios";
const {Header, Sider, Content, Footer} = Layout;
const {Text} = Typography;

const generateUUID = () => {
    return Math.random().toString(36).substring(2, 10).toUpperCase();
};

const Game = () => {
    const [messages, setMessages] = useState([]); // 聊天记录
    const [userMessage, setUserMessage] = useState(""); // 用户输入的消息
    const [loading, setLoading] = useState(false); // AI加载状态
    const chatContainerRef = useRef<HTMLDivElement>(null);
    const [game, setGame] = useState({}); // 存储回答内容的键值对字典
    const [gamelist,setGamelist]=useState([]);
    const [newName, setNewName] = useState("");
    const [columns, setColumns] = useState(1);
    const [isModalVisible, setIsModalVisible] = useState(false);
    const siderRef = useRef(null);
    const cardWidth = 250;
    const token = getToken();
    const scrollToBottom = () => {
        if (chatContainerRef.current) {
            // 使用 scrollHeight 来确保容器的内容已完全加载并滚动到底部
            chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
    };

    const sendMessage = async (question: string) => {
        const trimmedMessage = question.trim();
        if (!trimmedMessage) return;
        setLoading(true);

        const controller = new AbortController();
        try {
            const response = await fetch('http://localhost:8000/api/v1/game/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: trimmedMessage,
                    user_token: token
                }),
                signal: controller.signal
            });

            if (!response.body) {
                throw new Error("No response body");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");

            let fullAnswer = "";

            while (true) {
                const {value, done} = await reader.read();
                if (done) break;

                const lines = decoder.decode(value).split("\n").filter(Boolean);
                for (const line of lines) {
                    const data = JSON.parse(line);
                    if (data.type === "heartbeat") {
                        console.log("❤️ 心跳");
                    } else if (data.type === "answer") {
                        fullAnswer += data.text;
                    }
                }
            }
            return fullAnswer;

        } catch (error) {
            console.error("请求失败:", error);
        } finally {
            scrollToBottom();
            setLoading(false);
        }
    };

    const askname = async (question: string) => {
        setLoading(true);

        const response = await fetch('http://localhost:8000/api/v1/game/askname', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: question,
                    user_token: token
                }),
            });
            // 检查响应状态
            if (!response.ok) {
                console.error(`请求失败，状态码: ${response.status}`);
                throw new Error(`请求失败，状态码: ${response.status}`);
            }
            setLoading(true);

            // 解析返回的 JSON 数据
            const data = await response.json();
            return data; // 返回解析后的数据
    };

    const extractCode = async (answer: string) => {
        // 检查是否包含 <html> 开头和 </html> 结尾
        const htmlBlockMatch = answer.match(/(?:<!DOCTYPE html>\s*)?<html[\s\S]*?>[\s\S]*?<\/html>/i);
        if (htmlBlockMatch) {
            // 提取 HTML 内容
            const extractedCode = htmlBlockMatch[0].trim();
            // console.log(extractedCode);

            // 调用 askname 并等待其返回结果
            const nameResponse = await askname(extractedCode);
            const uuid = generateUUID(); // 生成随机UUID

            // 返回字典形式的结果
            return {
                uuid: uuid,
                name: nameResponse, // 假设 API 返回的内容是直接可用的名称
                code: extractedCode,
            };
        } else {
            // 如果没有 <html> 包裹，返回原始内容作为 code，同时 name 为 null
            return {
                name: null,
                code: answer.trim(),
            };
        }
    };

    async function handleAsk(query: string) {
        setMessages((prev) => [...prev, { sender: "user", text: query }]);
        const answer = await sendMessage(query);

        // 检查是否包含代码块
        const codeBlockMatch = answer.match(/<html[\s\S]*?>[\s\S]*?<\/html>/i);

        if (codeBlockMatch) {
            // 如果包含代码块，提取并清理代码内容

            const cleanedAnswer = await extractCode(answer);
            const uuid = generateUUID(); // 生成 UUID

            // 保存到 game 字典中
             setGame((prevGame) => ({
                ...prevGame,
                [uuid]: {
                    uuid: cleanedAnswer.uuid,
                    name: cleanedAnswer.name, // 从 extractCode 中获取 name
                    code: cleanedAnswer.code, // 从 extractCode 中获取 code
                },
            }));

            // 添加到聊天记录，标记为代码块
            setMessages((prev) => [
                ...prev,
                { sender: "bot", text: cleanedAnswer.code, uuid, isCode: true },
            ]);
        } else {
            // 如果没有代码块，直接添加到聊天记录，标记为普通文本
            setMessages((prev) => [
                ...prev,
                { sender: "bot", text: answer.trim(), isCode: false },
            ]);
        }
        setLoading(false);
    }

    const runHtmlCode = (code) => {
    // 打开新窗口
        const newWindow = window.open('', '_blank', 'width=1000,height=800');

        if (newWindow) {
          // 将HTML代码写入新窗口
          newWindow.document.open();
          newWindow.document.write(code);
          newWindow.document.close();
        } else {
          alert('弹出窗口被阻止，请允许弹出窗口后重试');
        }
      };

    const deleteGame = async (id) => {
        try {
            // 调用后端 DELETE API
            const response = await axios.delete(`http://127.0.0.1:8000/api/v1/game/delete/${id}`); // 替换为你的后端地址
            console.log(response); // 打印后端返回的结果
            message.success("游戏删除成功！");
            await fetchGames();
            return response // 返回删除成功的信息
        } catch (error) {
            // 处理错误
            if (error.response) {
                console.error(`Error: ${error.response.data.detail}`);
                alert(`删除失败: ${error.response.data.detail}`);
            } else {
                console.error(`Error: ${error.message}`);
                alert(`删除失败: ${error.message}`);
            }
            return null; // 返回 null 表示删除失败
        }
    };

    const updateGameName = async (uuid, newName) => {
        try {
            console.log(newName);
            console.log(uuid);
            const response = await axios.put(`http://127.0.0.1:8000/api/v1/game/update/${uuid}`,
                { new_name: newName },
                { headers: { 'Content-Type': 'application/json' } }
            );
            message.success("游戏名字修改成功");
            setIsModalVisible(false); // 关闭弹出框
            await fetchGames();
        } catch (error) {
            if (error.response) {
                console.error(`Error: ${error.response.data.detail}`);
                alert(`修改失败: ${error.response.data.detail}`);
            } else {
                console.error(`Error: ${error.message}`);
                alert(`修改失败: ${error.message}`);
            }
        }
    };

    const saveCode = async (game) => {
        try {
            const gameEntry = {
                uuid: game.uuid, // 新生成的 UUID
                code: game.code, // 从 game 中提取的 code
                name: game.name, // 从 game 中提取的 name
                url: "",    // 空的 URL（可根据需求填充）
            };
            // console.log("Game entry to save:", gameEntry);

            const response = await fetch('http://localhost:8000/api/v1/game/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(gameEntry), // 将对象转为 JSON 字符串
            });

            if (!response.ok) {
                message.error('游戏保存失败！');
            }else {
                message.success('游戏保存成功！');
                await fetchGames();
            }

        } catch (error) {
            console.error('保存失败:', error);
            alert('保存失败，请重试');
        }
    };

    const changeNameHandleOk = (game) => {
        if (!newName.trim()) {
            message.error("名字不能为空！");
            return;
        }
        updateGameName(game.uuid, newName.trim());
    };

    const changeNameHandleCancel = () => {
        setIsModalVisible(false); // 关闭弹出框
        setNewName(""); // 清空输入框
    };
    const showChangeNameModal = (game) => {
        setNewName(game.name); // 每次打开弹出框时，将输入框的值设置为当前名字
        setGame(game);
        setIsModalVisible(true); // 显示弹出框
    };
    async function fetchGames() {
      try {
        const response = await fetch("http://127.0.0.1:8000/api/v1/game/get_all", {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        // 检查响应是否成功
        if (!response.ok) {
          throw new Error(`HTTP error! Status: ${response.status}`);
        }

        // 解析 JSON 数据
        const games = await response.json();
        setGamelist(games);

        // 在前端展示游戏信息
      } catch (error) {
        console.error('Error fetching games:', error);
      }
    }

    useEffect(() => {
        fetchGames();

    }, []);
    // 自动滚动到最新消息
    useEffect(() => {
        if (chatContainerRef.current) {
            chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
    }, [messages]);

    useEffect(() => {
        const resizeObserver = new ResizeObserver((entries) => {
            for (let entry of entries) {
                const width = entry.contentRect.width;
                const newColumns = Math.max(1, Math.floor(width / cardWidth)); // 计算列数，至少 1 列
                setColumns(newColumns);
            }
        });

        if (siderRef.current) {
            resizeObserver.observe(siderRef.current);
        }

        return () => {
            if (siderRef.current) {
                resizeObserver.unobserve(siderRef.current);
            }
        };
    }, [cardWidth]);

    return (
        <Layout style={{height: "80vh", backgroundColor: "#F5F5F5"}}>
            <Splitter
                style={{ display: "flex", height: "100%" }}
            >
                <Splitter.Panel collapsible >
                    <Layout>
                        <div
                            style={{
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                height: "80vh",
                                padding: "16px",
                                backgroundColor: "#ffffff",
                            }}
                        >
                            {/* 聊天记录容器 */}
                            <div
                                style={{
                                    flex: 1,
                                    overflowY: "auto",
                                    border: "1px solid #e8e8e8",
                                    borderRadius: "8px",
                                    padding: "16px",
                                    backgroundColor: "#f5f5f5",
                                    marginBottom: "16px",
                                }}
                                ref={chatContainerRef}
                            >
                                {messages.map((msg, index) => (
                                    msg.sender === "bot" ? (
                                        msg.isCode ? (
                                            // 如果是代码块，渲染矩形运行框
                                            <div key={index} style={{
                                                border: "1px solid #e8e8e8",
                                                borderRadius: "8px",
                                                padding: "16px",
                                                marginBottom: "16px",
                                                backgroundColor: "#ffffff",
                                            }}>
                                                <div
                                                    style={{
                                                        display: "flex",
                                                        justifyContent: "space-between",
                                                        alignItems: "center",
                                                        borderRadius: "8px",
                                                        backgroundColor: "#ffffff",
                                                    }}
                                                >
                                                    {/* 左侧内容：显示名称 */}
                                                    <div style={{fontWeight: "bold", fontSize: "16px", color: "#333"}}>
                                                        {game[msg.uuid]?.name || "新游戏"} {/* 动态显示名称 */}
                                                    </div>
                                                    {/* 右侧按钮区域 */}
                                                    <div
                                                        style={{
                                                            display: "flex",
                                                            flexDirection: "column",
                                                            alignItems: "center",
                                                            gap: "8px",
                                                        }}
                                                    >
                                                        <Button
                                                            onClick={() => {
                                                                const newHtmlCode = game[msg.uuid].code;
                                                                runHtmlCode(newHtmlCode); // 更新 htmlCode
                                                            }}
                                                        >
                                                            <CaretRightOutlined/>运行
                                                        </Button>

                                                        <Button
                                                            onClick={() => saveCode(game[msg.uuid])}
                                                        >
                                                            <VerticalAlignBottomOutlined/>保存
                                                        </Button>
                                                    </div>
                                                </div>
                                            </div>
                                        ) : (
                                            // 如果不是代码块，渲染普通对话框
                                            <div key={index} style={{ textAlign: "left" }}>
                                                <div
                                                    style={{
                                                        display: "inline-block",
                                                        margin: "5px",
                                                        padding: "10px",
                                                        borderRadius: "5px",
                                                        backgroundColor: "#f0f0f0",
                                                        whiteSpace: "pre-line",
                                                        lineHeight: "1.5",
                                                    }}
                                                >
                                                    {msg.text.replace(/[#*-]/g, "")}
                                                </div>
                                            </div>
                                        )
                                    ) : (
                                        // 用户消息
                                        <div key={index} style={{ textAlign: "right" }}>
                                            <div
                                                style={{
                                                    display: "inline-block",
                                                    margin: "5px",
                                                    padding: "10px",
                                                    borderRadius: "5px",
                                                    backgroundColor: "#e6f7ff",
                                                    whiteSpace: "pre-line",
                                                    lineHeight: "1.5",
                                                }}
                                            >
                                                {msg.text.replace(/[#*-]/g, "")}
                                            </div>
                                        </div>
                                    )
                                ))}
                                {loading && messages.length > 0 && messages[messages.length - 1].sender === "user" && (
                                    <div style={{textAlign: "left", padding: "10px"}}>
                                        <Spin tip="思考中..."/>
                                    </div>
                                )}
                            </div>

                            {/* 输入框与发送按钮 */}
                            <div
                                style={{
                                    display: "flex",
                                    gap: "10px",
                                    width: "100%",
                                    justifyContent: "center",
                                }}
                            >
                        <Input
                            value={userMessage}
                            onChange={(e) => setUserMessage(e.target.value)}
                            onPressEnter={(e) => {
                                e.preventDefault();
                                handleAsk(userMessage); // 传递用户消息
                                setUserMessage(""); // 清空输入框
                            }}
                            placeholder="请告诉我您想做的游戏内容..."
                            style={{
                                flex: 1,
                                borderRadius: "4px",
                                border: "1px solid #e8e8e8",
                                padding: "8px",
                            }}
                        />
                        <Button
                            onClick={() => {
                                handleAsk(userMessage);
                                setUserMessage("");
                            }}
                            loading={loading}
                            style={{
                                height:"100%",
                                borderRadius: "4px",
                            }}
                        >
                            {loading ? "生成中..." : "发送"}
                        </Button>
                    </div>
                </div>
                    </Layout>
                </Splitter.Panel>
                <Splitter.Panel defaultSize={250} min={250}>
                    <div
                        ref={siderRef} // 绑定 ref 用于监听宽度
                        style={{
                            height: "100%",
                            backgroundColor: "#FFFFFF",
                            borderLeft: "1px solid #E8E8E8",
                            display: "flex",
                            flexDirection: "column",
                        }}
                    >
                        {gamelist.length === 0 ? (
                            <div
                                style={{
                                    flex: 1,
                                    display: "flex",
                                    flexDirection: "column",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    color: "#999",
                                }}
                            >
                                <MailOutlined style={{fontSize: 48, marginTop: 16, marginBottom: 16, color: "#999"}}/>
                                <Text style={{color: "#999"}}>暂无数据</Text>
                            </div>
                        ) : (
                            <div
                                style={{
                                    flex: 1,
                                    display: "grid",
                                    gridTemplateColumns: `repeat(${columns}, 1fr)`, // 动态列数
                                    gridGap: "16px", // 间距
                                    padding: "16px",
                                    overflowY: "auto", // 滚动
                                }}
                            >
                                {gamelist.map((game, index) => (
                                    <div
                                        key={index}
                                        style={{
                                            border: "1px solid #e8e8e8",
                                            borderRadius: "8px",
                                            padding: "16px",
                                            backgroundColor: "#ffffff",
                                            height: "150px", // 固定高度
                                            display: "flex", // 让内容居中
                                            flexDirection: "column", // 垂直布局
                                            justifyContent: "space-between", // 内容上下分布
                                        }}
                                    >
                                        <div
                                            style={{
                                                display: "flex",
                                                justifyContent: "space-between",
                                                alignItems: "center",
                                                borderRadius: "8px",
                                                backgroundColor: "#ffffff",
                                            }}
                                        >
                                            {/* 左侧内容：显示名称 */}
                                            <div style={{fontWeight: "bold", fontSize: "16px", color: "#333"}}>
                                                {game.name || "新游戏"}
                                            </div>

                                            {/* 右侧按钮区域 */}
                                            <div
                                                style={{
                                                    display: "flex",
                                                    flexDirection: "column",
                                                    alignItems: "center",
                                                    gap: "8px",
                                                }}
                                            >
                                                <Button
                                                    onClick={() => {
                                                        runHtmlCode(game.code);
                                                    }}
                                                >
                                                    <CaretRightOutlined/>
                                                </Button>
                                                <Button
                                                    onClick={() => {
                                                        showChangeNameModal(game); // 显示弹出框
                                                    }}
                                                >
                                                    <EditOutlined />
                                                </Button>

                                                <Popconfirm
                                                    title={`确定要删除游戏 "${game.name}" 吗?`}
                                                    onConfirm={() => deleteGame(game.uuid)} // 点击确认按钮时调用 deleteGame
                                                    okText="Yes"
                                                    cancelText="No"
                                                >
                                                    <Button danger>
                                                        <ClearOutlined />
                                                    </Button>
                                                </Popconfirm>

                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </Splitter.Panel>
            </Splitter>
            <Modal
                title="修改游戏名字"
                visible={isModalVisible}
                onOk={()=>changeNameHandleOk(game)} // 确定按钮逻辑
                onCancel={changeNameHandleCancel} // 取消按钮逻辑
                okText="确认"
                cancelText="取消"
            >
                <Input
                    placeholder="请输入新的游戏名字"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)} // 更新输入框内容
                />
            </Modal>
        </Layout>
    );
};

export default Game;
