<?php
// This file contains dangerous PHP code that should never be executed.
// migrate-guard should analyze it without side effects.

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

// Set a global variable to prove the code is not executed
if (!defined('BOOBY_TRAP_LARAVEL_EXECUTED')) {
    define('BOOBY_TRAP_LARAVEL_EXECUTED', false);
}

class PushBoobyTrapEval extends Migration
{
    public function up()
    {
        // This backtick execution would run if the migration was executed
        // But migrate-guard should never evaluate this
        $dangerous = `echo "EXECUTED"`;

        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn('old_field');
        });
    }

    public function down()
    {
    }
}
