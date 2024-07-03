#!/usr/bin/env python3

import asyncio
import logging


class Shell:
    logger = logging.getLogger(__name__)

    def __init__(self, addr, bot, loop=None):
        ''' addr: str, bot: cytube_bot.CytubeBot, loop: asyncio.AbstractEventLoop'''
        if addr is None:
            self.logger.warning('shell is disabled')
            self.host = None
            self.port = None
            self.loop = None
            self.bot = None
            self.task = None
            return

        self.host, self.port = addr.rsplit(':')
        self.port = int(self.port)
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.bot = bot

        self.logger.info('starting shell at %s:%d', self.host, self.port)
        self.task = loop.create_task(
            asyncio.start_server(
                self.handle_connection,
                self.host, self.port,
                loop=self.loop
            )
        )

    @staticmethod
    async def write(writer, string):
        ''' Async function to write to a writer object '''
        writer.write(string.encode('utf-8'))
        await writer.drain()

    def close(self):
        ''' Close the shell server '''
        if self.task is not None:
            self.logger.info('cancel shell task')
            self.task.cancel()

    async def handle_connection(self, reader, writer):
        ''' Async function to handle a connection '''
        try:
            from cytube_bot import MediaLink, MessageParser
            bot = self.bot

            cmd = ''
            res = None

            self.logger.info('accepted shell connection')

            while True:
                await self.write(writer, '\\ ' if cmd else '>>> ')
                line = await reader.readline()
                line = line.decode('utf-8')
                if line.endswith('|\n'):
                    cmd += line[:-2]
                    cmd += '\n'
                    continue
                cmd += line
                if line.endswith('\\\n'):
                    continue

                if cmd.startswith('exit') or cmd.startswith('quit'):
                    self.logger.info('exiting shell')
                    await self.write(writer, 'exiting\n')
                    break

                try:
                    res = eval(cmd)
                    if asyncio.iscoroutine(res):
                        res = await res
                except asyncio.CancelledError as ex:
                    raise ex
                except Exception as ex:
                    res = ex
                finally:
                    cmd = ''

                await self.write(writer, '%r\n' % res)
        except IOError as ex:
            self.logger.error('connection error: %r', ex)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except AttributeError:
                pass
