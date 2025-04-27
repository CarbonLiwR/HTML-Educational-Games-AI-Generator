create table game
(
    id   int auto_increment
        primary key,
    uuid varchar(20)  null,
    name varchar(255) null,
    url  varchar(255) null,
    code longtext     null,
    rules longtext     null
);

create table game_chat_history
(
    id           int auto_increment
        primary key,
    user_uuid    text not null,
    chat_history text null
);

