import sqlite3

def create_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tg_users (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            is_admin BOOL DEFAULT FALSE,
            access_token TEXT,
            refresh_token TEXT,
            token_id TEXT,
            device_id TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vk_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT,
            group_link TEXT,
            description TEXT,
            group_id INTEGER
        )
    ''')

    conn.commit()

def get_users():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT tg_id, refresh_token, device_id FROM tg_users WHERE is_admin = 1")
    return cursor.fetchall()

def get_vk_groups():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT group_id, group_name FROM vk_groups")
    groups = cursor.fetchall()
    conn.close()
    return groups

def get_vk_group_id_by_name(group_id: str):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT group_name FROM vk_groups WHERE group_id = ?", (group_id,))
        result = cursor.fetchone()  
        
        if result:
            return result[0]       
        else:
            return None  
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return None  
    finally:
        conn.close() 

def add_user_if_not_exists(tg_id, username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tg_users WHERE tg_id=?", (tg_id,))
    result = cursor.fetchone()
    
    if result is None:
        cursor.execute("INSERT INTO tg_users (tg_id, username) VALUES (?, ?)", (tg_id, username))
        conn.commit()
    
    conn.close()

def update_token_info(tg_id, token, refresh_token, token_id, device_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE tg_users SET access_token = ?, refresh_token = ?, token_id = ?, device_id = ? WHERE tg_id = ?", (token, refresh_token, token_id, device_id, tg_id))
        conn.commit()  
        return True  
    except Exception as e:
        print(f"Ошибка при обновлении токена: {e}")
        return False  
    finally:
        conn.close()  

def update_token(tg_id, token, r_token):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE tg_users SET access_token = ?, refresh_token = ? WHERE tg_id = ?", (token, r_token, tg_id))
        conn.commit()  
        return True  
    except Exception as e:
        print(f"Ошибка при обновлении токена: {e}")
        return False  
    finally:
        conn.close()  

def save_vk_group(group_link, group_name, description, group_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO vk_groups (group_name, group_link, description, group_id)
        VALUES (?, ?, ?, ?)
    ''', (group_name, group_link, description, group_id))
    
    conn.commit()
    conn.close()

def set_user_admin(username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE tg_users SET is_admin = 1 WHERE username = ?", (username,))
    except Exception as e:
        raise e
    
    conn.commit()

def revoke_admin_rights(username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE tg_users SET is_admin = ? WHERE username = ?", (False, username))
        conn.commit()  
        
        if cursor.rowcount > 0:
            print(f"Права администратора успешно отменены для пользователя: {username}")
            return True  
        else:
            raise Exception() 
    except Exception as e:
        raise e
    finally:
        conn.close() 

def get_token_by_tg_id(tg_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT access_token FROM tg_users WHERE tg_id = ?", (tg_id,))
        result = cursor.fetchone() 
        
        if result:
            return result[0]  
        else:
            return None  
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return None  
    finally:
        conn.close()  

def delete_vk_group(group_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM vk_groups WHERE group_id = ?", (group_id,))
        conn.commit()
        return True  
    except Exception as e:
        print(f"Ошибка при удалении группы: {e}")
        return False  
    finally:
        conn.close()

def update_group_description(group_id, new_description):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE vk_groups SET description = ? WHERE group_id = ?", (new_description, group_id))
        conn.commit()
        return True  
    except Exception as e:
        print(f"Ошибка при обновлении описания группы: {e}")
        return False 
    finally:
        conn.close()

def get_group_description(group_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT description FROM vk_groups WHERE group_id = ?", (group_id,))
        result = cursor.fetchone()  
        
        if result:
            return result[0]       
        else:
            return None  
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return None  
    finally:
        conn.close() 

def get_group_link(group_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT group_link FROM vk_groups WHERE group_id = ?", (group_id,))
        result = cursor.fetchone()  
        
        if result:
            return result[0]       
        else:
            return None  
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return None  
    finally:
        conn.close() 

create_db()
set_user_admin('dezot01')