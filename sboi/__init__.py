"""Project package.

cPanel / MariaDB note
---------------------
Shared cPanel hosting rarely has the MySQL development headers needed to
compile ``mysqlclient``, so this project talks to MariaDB through the
pure-Python ``PyMySQL`` driver. Django's MySQL backend imports the driver as
``MySQLdb``, so we register PyMySQL under that name and report a driver
version Django accepts (Django 6.1 requires ``version_info >= (2, 2, 1)``).

If the real ``mysqlclient`` is installed it is used as-is. The imports are
guarded so plain SQLite development keeps working with no MySQL driver.
"""
try:
    import MySQLdb  # noqa: F401  (real mysqlclient, preferred when present)
except ImportError:
    try:
        import pymysql

        # Present a MySQLdb-compatible version: PyMySQL is API-compatible but
        # reports its own (1.x) version, which Django rejects.
        pymysql.version_info = (2, 2, 1, 'final', 0)
        pymysql.__version__ = '2.2.1'
        pymysql.install_as_MySQLdb()
    except ImportError:  # pragma: no cover - only needed for MariaDB/MySQL
        pass
