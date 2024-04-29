# -*- coding: utf-8 -*-
import logging
import os
import sqlite3
from time import time

from util import Cache


class Database(object):
    dir_path = os.path.dirname(os.path.abspath(__file__))

    _instance = None
    _initialized = False
    _banned_users = set()

    def __new__(cls):
        if not Database._instance:
            Database._instance = super(Database, cls).__new__(cls)
        return Database._instance

    def __init__(self):
        if self._initialized:
            return

        database_path = os.path.join(self.dir_path, "users.db")
        self.logger = logging.getLogger(__name__)

        if not os.path.exists(database_path):
            self.logger.debug("File '{}' does not exist! Trying to create one.".format(database_path))
        try:
            self.create_database(database_path)
        except Exception:
            self.logger.error("An error has occurred while creating the database!")

        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.text_factory = lambda x: str(x, 'utf-8', "ignore")
        self.cursor = self.connection.cursor()

        self.load_banned_users()

        self._initialized = True

    @staticmethod
    def create_database(database_path):
        """
        Create database file and add admin and users table to the database
        :param database_path:
        :return:
        """
        open(database_path, 'a').close()

        connection = sqlite3.connect(database_path)
        connection.text_factory = lambda x: str(x, 'utf-8', "ignore")
        cursor = connection.cursor()

        cursor.execute("CREATE TABLE IF NOT EXISTS 'admins' "
                       "('user_id' INTEGER NOT NULL,"
                       "'first_name' TEXT,"
                       "'username' TEXT,"
                       "PRIMARY KEY('user_id'));")

        cursor.execute("CREATE TABLE IF NOT EXISTS 'users'"
                       "('user_id' INTEGER NOT NULL,"
                       "'first_name' TEXT,"
                       "'last_name' TEXT,"
                       "'username' TEXT,"
                       "'games_played' INTEGER DEFAULT 0,"
                       "'games_won' INTEGER DEFAULT 0,"
                       "'games_tie' INTEGER DEFAULT 0,"
                       "'last_played' INTEGER DEFAULT 0,"
                       "'banned' INTEGER DEFAULT 0,"
                       "PRIMARY KEY('user_id'));")

        cursor.execute("CREATE TABLE IF NOT EXISTS 'chats'"
                       "('chat_id' INTEGER NOT NULL,"
                       "'lang_id' TEXT NOT NULL DEFAULT 'en',"
                       "PRIMARY KEY('chat_id'));")
        connection.commit()
        connection.close()

    def load_banned_users(self):
        """Loads all banned users from the database into a list"""
        self.cursor.execute("SELECT user_id FROM users WHERE banned=1;")
        result = self.cursor.fetchall()

        if not result:
            return

        for row in result:
            self._banned_users.add(int(row["user_id"]))

    def get_banned_users(self):
        """Returns a list of all banned user_ids"""
        return self._banned_users

    def get_user(self, user_id):
        self.cursor.execute("SELECT user_id, first_name, last_name, username, games_played, games_won, games_tie, last_played, banned"
                            " FROM users WHERE user_id=?;", [str(user_id)])

        result = self.cursor.fetchone()
        if not result or len(result) == 0:
            return None
        return result

    def is_user_banned(self, user_id):
        """Checks if a user was banned by the admin of the bot from using it"""
        # user = self.get_user(user_id)
        # return user is not None and user[8] == 1
        return int(user_id) in self._banned_users

    def ban_user(self, user_id):
        """Bans a user from using a the bot"""
        self.cursor.execute("UPDATE users SET banned=1 WHERE user_id=?;", [str(user_id)])
        self.connection.commit()
        self._banned_users.add(int(user_id))

    def unban_user(self, user_id):
        """Unbans a user from using a the bot"""
        self.cursor.execute("UPDATE users SET banned=0 WHERE user_id=?;", [str(user_id)])
        self.connection.commit()
        self._banned_users.remove(int(user_id))

    def get_recent_players(self):
        one_day_in_secs = 60 * 60 * 24
        current_time = int(time())
        self.cursor.execute("SELECT user_id FROM users WHERE last_played>=?;", [current_time - one_day_in_secs])

        return self.cursor.fetchall()

    def get_played_games(self, user_id):
        self.cursor.execute("SELECT games_played FROM users WHERE user_id=?;", [str(user_id)])
        result = self.cursor.fetchone()

        if not result or len(result) <= 0:
            return 0

        return int(result["games_played"])

    @Cache(timeout=60)
    def get_admins(self):
        self.cursor.execute("SELECT user_id from admins;")
        admins = self.cursor.fetchall()
        admin_list = []
        for admin in admins:
            admin_list.append(admin["user_id"])
        return admin_list

    @Cache(timeout=120)
    def get_lang_id(self, chat_id):
        self.cursor.execute("SELECT lang_id FROM chats WHERE chat_id=?;", [str(chat_id)])
        result = self.cursor.fetchone()

        if not result or not result["lang_id"]:
            # Make sure that the database stored an actual value and not "None"
            return "en"

        return result["lang_id"]

    def set_lang_id(self, chat_id, lang_id):
        if lang_id is None:
            lang_id = "en"
        Cache().invalidate_lang_cache(chat_id)
        try:
            self.cursor.execute("INSERT INTO chats (chat_id, lang_id) VALUES(?, ?);", [chat_id, lang_id])
        except sqlite3.IntegrityError:
            self.cursor.execute("UPDATE chats SET lang_id = ? WHERE chat_id = ?;", [lang_id, chat_id])
        self.connection.commit()

    def add_user(self, user_id, lang_id, first_name, last_name, username):
        if self.is_user_saved(user_id):
            return
        self._add_user(user_id, lang_id, first_name, last_name, username)

    def _add_user(self, user_id, lang_id, first_name, last_name, username):
        try:
            self.cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0);", [str(user_id), first_name, last_name, username])
            self.cursor.execute("INSERT INTO chats VALUES (?, ?);", [str(user_id), lang_id])
            self.connection.commit()
        except sqlite3.IntegrityError:
            return

    def set_games_won(self, games_won, user_id):
        self.cursor.execute("UPDATE users SET games_won = ? WHERE user_id = ?;", [games_won, str(user_id)])
        self.connection.commit()

    def set_games_played(self, games_played, user_id):
        self.cursor.execute("UPDATE users SET games_played = ? WHERE user_id = ?;", [games_played, str(user_id)])
        self.connection.commit()

    def set_last_played(self, last_played, user_id):
        self.cursor.execute("UPDATE users SET last_played = ? WHERE user_id = ?;", [last_played, str(user_id)])
        self.connection.commit()

    def is_user_saved(self, user_id):
        self.cursor.execute("SELECT rowid, * FROM users WHERE user_id=?;", [str(user_id)])

        result = self.cursor.fetchall()
        if len(result) > 0:
            return True
        else:
            return False

    def user_data_changed(self, user_id, first_name, last_name, username):
        self.cursor.execute("SELECT * FROM users WHERE user_id=?;", [str(user_id)])
        result = self.cursor.fetchone()

        # check if user is saved
        if not result:
            return True

        if result["first_name"] == first_name and result["last_name"] == last_name and result["username"] == username:
            return False

        return True

    def update_user_data(self, user_id, first_name, last_name, username):
        self.cursor.execute("UPDATE users SET first_name=?, last_name=?, username=? WHERE user_id=?;", [first_name, last_name, username, str(user_id)])
        self.connection.commit()

    def reset_stats(self, user_id):
        self.cursor.execute("UPDATE users SET games_played='0', games_won='0', games_tie='0', last_played='0' WHERE user_id=?;", [str(user_id)])
        self.connection.commit()

    def close_conn(self):
        self.connection.close()
