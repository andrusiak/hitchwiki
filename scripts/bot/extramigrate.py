#
# Migrate extras (comments, ratings and waiting times) from old (pre-Feb 2015)
# Hitchwiki maps DB:
#
# - hitchwiki_maps.t_comments
# - hitchwiki_maps.t_waitingtimes
# - hitchwiki_maps.t_ratings
#
# to the tables of the new custom MediaWiki extensions:
#
# - HWComments:
#   - hitchwiki_en.hw_comments
#   - hitchwiki_en.hw_comments_count
# - HWRatings:
#   - hitchwiki_en.hw_ratings
#   - hitchwiki_en.hw_ratings_avg
# - HWWaitingTime:
#   - hitchwiki_en.hw_waiting_time
#   - hitchwiki_en.hw_waiting_time_avg
#
# Relies on hitchwiki_maps.point_page_mappings table generated by spotmigrate.py
#

import ConfigParser
import MySQLdb

settings = ConfigParser.ConfigParser()
settings.read('../../configs/settings.ini')
dummy_user_id = 0

db = MySQLdb.connect(
    host=settings.get('db', 'host'),
    user=settings.get('db', 'username'),
    passwd=settings.get('db', 'password'),
    db=settings.get('db', 'database'),
    charset='utf8'
)

print 'hw_comments: truncate...'

comments_del_cur = db.cursor()
comments_del_cur.execute(
    'TRUNCATE hitchwiki_en.hw_comments'
)
db.commit()
print '--> affected rows: %d' % (comments_del_cur.rowcount)

print 'hw_comments: import...'

comments_cur = db.cursor()
comments_cur.execute((
    'INSERT INTO hitchwiki_en.hw_comments' +
        ' (hw_comment_id, hw_user_id, hw_page_id, hw_timestamp, hw_commenttext)' +
    " SELECT c.id, COALESCE(c.fk_user, %s), ppm.page_id, DATE_FORMAT(c.datetime, '%%Y%%m%%d%%H%%i%%S'), c.comment" +
        ' FROM hitchwiki_maps.t_comments AS c' +
        ' LEFT JOIN hitchwiki_maps.point_page_mappings AS ppm' +
            ' ON ppm.point_id = c.fk_place' +
        ' WHERE ppm.page_id IS NOT NULL' # import comments only for imported spots
) % (dummy_user_id))
db.commit()
print '--> affected rows: %d' % (comments_cur.rowcount)

print 'hw_comments_count: truncate...'

comments_count_del_cur = db.cursor()
comments_count_del_cur.execute(
    'TRUNCATE hitchwiki_en.hw_comments_count'
)
db.commit()
print '--> affected rows: %d' % (comments_count_del_cur.rowcount)

print 'hw_comments_count: recalculate...'

comment_count_cur = db.cursor()
comment_count_cur.execute(
    'INSERT INTO hitchwiki_en.hw_comments_count' +
        ' (hw_page_id, hw_comments_count)' +
    ' SELECT hw_page_id, COUNT(*)' +
        ' FROM hitchwiki_en.hw_comments' +
        ' GROUP BY hw_page_id'
)
db.commit()
print '--> affected rows: %d' % (comment_count_cur.rowcount)

print ''

print 'hw_waiting_time: truncate...'

waiting_times_del_cur = db.cursor()
waiting_times_del_cur.execute(
    'TRUNCATE hitchwiki_en.hw_waiting_time'
)
db.commit()
print '--> affected rows: %d' % (waiting_times_del_cur.rowcount)

print 'hw_waiting_time: import...'

waiting_times_cur = db.cursor()
waiting_times_cur.execute((
    'INSERT INTO hitchwiki_en.hw_waiting_time' +
        ' (hw_waiting_time_id, hw_user_id, hw_page_id, hw_timestamp, hw_waiting_time)' +
    " SELECT w.id, COALESCE(w.fk_user, %s), ppm.page_id, DATE_FORMAT(w.datetime, '%%Y%%m%%d%%H%%i%%S'), w.waitingtime" +
        ' FROM hitchwiki_maps.t_waitingtimes AS w' +
        ' LEFT JOIN hitchwiki_maps.point_page_mappings AS ppm' +
            ' ON ppm.point_id = w.fk_point' +
        ' WHERE ppm.page_id IS NOT NULL' # import waiting times only for imported spots
) % (dummy_user_id))
db.commit()
print '--> affected rows: %d' % (waiting_times_cur.rowcount)

print 'hw_waiting_time_avg: truncate...'

waiting_times_avg_del_cur = db.cursor()
waiting_times_avg_del_cur.execute(
    'TRUNCATE hitchwiki_en.hw_waiting_time_avg'
)
db.commit()
print '--> affected rows: %d' % (waiting_times_avg_del_cur.rowcount)

print 'hw_waiting_time_avg: recalculate (slow)...'

# Tricky to find the median on the database side, so do it in client code
waiting_time_all_cur = db.cursor(MySQLdb.cursors.DictCursor)
waiting_time_all_cur.execute(
    "SELECT hw_page_id, COUNT(*) AS count_wt, MIN(hw_waiting_time) AS min_wt, MAX(hw_waiting_time) AS max_wt," +
            " GROUP_CONCAT(hw_waiting_time ORDER BY hw_waiting_time SEPARATOR ';') AS waiting_times" +
        ' FROM hitchwiki_en.hw_waiting_time' +
        ' GROUP BY hw_page_id'
)
for wt_group in waiting_time_all_cur.fetchall():
    waiting_times = wt_group['waiting_times'].split(';')
    count = len(waiting_times)

    if count & 1: # odd number of waiting times; median is the middle number
        median = int(waiting_times[(count - 1) / 2])
    else: # even number of waiting times; median is the mean value of the two middle numbers
        middle1 = float(waiting_times[count / 2 - 1])
        middle2 = float(waiting_times[count / 2])
        median = (middle1 + middle2) / 2

    waiting_time_median_cur = db.cursor()
    waiting_time_median_cur.execute((
        "INSERT INTO hitchwiki_en.hw_waiting_time_avg" +
            ' (hw_page_id, hw_average_waiting_time, hw_count_waiting_time, hw_min_waiting_time, hw_max_waiting_time)' +
            ' VALUES (%d, %f, %d, %d, %d)'
    ) % (wt_group['hw_page_id'], median, wt_group['count_wt'], wt_group['min_wt'], wt_group['max_wt']))
    db.commit()
print '--> affected rows: ~ %d' % (waiting_time_all_cur.rowcount)

print ''

print 'hw_ratings: truncate...'

ratings_del_cur = db.cursor()
ratings_del_cur.execute(
    'TRUNCATE hitchwiki_en.hw_ratings'
)
db.commit()
print '--> affected rows: %d' % (ratings_del_cur.rowcount)

print 'hw_ratings: import (for spots)...'

ratings_cur = db.cursor()
ratings_cur.execute((
    'INSERT INTO hitchwiki_en.hw_ratings' +
        ' (hw_rating_id, hw_user_id, hw_page_id, hw_timestamp, hw_rating)' +
    " SELECT r.id, COALESCE(r.fk_user, %s), ppm.page_id, DATE_FORMAT(r.datetime, '%%Y%%m%%d%%H%%i%%S'), 6 - r.rating" +
        ' FROM hitchwiki_maps.t_ratings AS r' +
        ' LEFT JOIN hitchwiki_maps.point_page_mappings AS ppm' +
            ' ON ppm.point_id = r.fk_point' +
        ' WHERE r.rating <> 0' + # ignore "none" ratings
            ' AND ppm.page_id IS NOT NULL' # import ratings only for imported spots
) % (dummy_user_id))
db.commit()
print '--> affected rows: %d' % (ratings_cur.rowcount)

print 'hw_ratings_avg: truncate...'

ratings_avg_del_cur = db.cursor()
ratings_avg_del_cur.execute(
    'TRUNCATE hitchwiki_en.hw_ratings_avg'
)
db.commit()
print '--> affected rows: %d' % (ratings_avg_del_cur.rowcount)

print 'hw_ratings_avg: recalculate...'

rating_avg_cur = db.cursor()
rating_avg_cur.execute(
    'INSERT INTO hitchwiki_en.hw_ratings_avg' +
        ' (hw_page_id, hw_count_rating, hw_average_rating)' +
    ' SELECT hw_page_id, COUNT(*), CAST(AVG(hw_rating) AS DECIMAL(5, 4))' +
        ' FROM hitchwiki_en.hw_ratings' +
        ' GROUP BY hw_page_id'
)
db.commit()
print '--> affected rows: %d' % (rating_avg_cur.rowcount)

print ''

# Don't do this, not to lose freshly imported spot ratings
# print 'hw_ratings: truncate...'

# ratings_del_cur = db.cursor()
# ratings_del_cur.execute(
#     'TRUNCATE hitchwiki_en.hw_ratings'
# )
# db.commit()
# print '--> affected rows: %d' % (ratings_del_cur.rowcount)

print 'hw_ratings: import (for countries)...'

ratings_cur = db.cursor()
ratings_cur.execute((
    'INSERT INTO hitchwiki_en.hw_ratings' +
        ' (hw_user_id, hw_page_id, hw_timestamp, hw_rating)' +
    " SELECT COALESCE(u.user_id, %s), p.page_id, DATE_FORMAT(r.timestamp, '%%Y%%m%%d%%H%%i%%S'), r.rating" + # country ratings are not inverted
        ' FROM hitchwiki_rate.ratings AS r' +
        ' LEFT JOIN hitchwiki_maps.countryinfo_ext AS c' +
            ' ON c.bad_alpha2 = r.country' +
        ' INNER JOIN hitchwiki_en.page AS p' + # *all* ratings should have an existing corresponding country page
            ' ON p.page_title COLLATE latin1_bin = c.wiki_name' +
                ' AND p.page_namespace = 0' +
                ' AND p.page_is_redirect = 0' +
        ' LEFT JOIN hitchwiki_en.user AS u' +
            ' ON u.user_name = r.user'
) % (dummy_user_id))
db.commit()
print '--> affected rows: %d' % (ratings_cur.rowcount)

print 'hw_ratings_avg: truncate...'

ratings_avg_del_cur = db.cursor()
ratings_avg_del_cur.execute(
    'TRUNCATE hitchwiki_en.hw_ratings_avg'
)
db.commit()
print '--> affected rows: %d' % (ratings_avg_del_cur.rowcount)

print 'hw_ratings_avg: recalculate...'

rating_avg_cur = db.cursor()
rating_avg_cur.execute(
    'INSERT INTO hitchwiki_en.hw_ratings_avg' +
        ' (hw_page_id, hw_count_rating, hw_average_rating)' +
    ' SELECT hw_page_id, COUNT(*), CAST(AVG(hw_rating) AS DECIMAL(5, 4))' +
        ' FROM hitchwiki_en.hw_ratings' +
        ' GROUP BY hw_page_id'
)
db.commit()
print '--> affected rows: %d' % (rating_avg_cur.rowcount)
